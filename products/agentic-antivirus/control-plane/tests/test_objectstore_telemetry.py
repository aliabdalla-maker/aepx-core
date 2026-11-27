"""BE-05 object storage (OCI Object Storage S3-compatible API, SigV4) and BE-06 OpenTelemetry traces."""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import objectstore
from conftest import CP


def test_sigv4_matches_the_published_aws_example():
    # AWS S3 documentation, "Signature Calculations for the Authorization Header", GET Object example.
    h = objectstore.sign_v4(method="GET", url="https://examplebucket.s3.amazonaws.com/test.txt",
                            headers={"Range": "bytes=0-9"}, payload_sha256=objectstore.EMPTY_SHA256,
                            access_key="AKIAIOSFODNN7EXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                            region="us-east-1", now=datetime(2013, 5, 24, tzinfo=timezone.utc))
    assert h["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


class _FakeS3(BaseHTTPRequestHandler):
    objects: dict[str, bytes] = {}
    secret = "test-secret"

    def log_message(self, *a):
        pass

    def _authorised(self, body: bytes) -> bool:
        auth = self.headers.get("authorization", "")
        signed = auth.split("SignedHeaders=")[1].split(",")[0].split(";")
        hdrs = {k: self.headers[k] for k in signed if k not in ("host", "x-amz-date", "x-amz-content-sha256")}
        if hashlib.sha256(body).hexdigest() != self.headers["x-amz-content-sha256"]:
            return False
        now = datetime.strptime(self.headers["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        want = objectstore.sign_v4(method=self.command, url=f"http://{self.headers['host']}{self.path}", headers=hdrs,
                                   payload_sha256=self.headers["x-amz-content-sha256"], access_key="AK",
                                   secret_key=self.secret, region="uk-london-1", now=now)
        return want["authorization"] == auth

    def _do(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        if not self._authorised(body):
            self.send_response(403); self.end_headers(); return
        if self.command == "PUT":
            self.objects[self.path] = body
            self.send_response(200); self.send_header("ETag", '"e"'); self.end_headers(); return
        if self.path not in self.objects:
            self.send_response(404); self.end_headers(); return
        if self.command == "DELETE":
            del self.objects[self.path]; self.send_response(204); self.end_headers(); return
        data = self.objects[self.path]
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        if self.command == "GET":
            self.wfile.write(data)

    do_PUT = do_GET = do_HEAD = do_DELETE = _do


@pytest.fixture()
def fake_s3():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeS3)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _store(endpoint, secret="test-secret"):
    return objectstore.ObjectStore(endpoint, "uk-london-1", "aav-backups", "AK", secret, check_egress=False)


def test_put_get_head_delete_round_trip(fake_s3):
    s = _store(fake_s3)
    data = b"Salted__" + bytes(range(256)) * 40
    meta = s.put("backups/aav-20261127T030000Z.dump.enc", data)
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    assert s.exists("backups/aav-20261127T030000Z.dump.enc")
    assert s.get("backups/aav-20261127T030000Z.dump.enc") == data
    s.delete("backups/aav-20261127T030000Z.dump.enc")
    assert not s.exists("backups/aav-20261127T030000Z.dump.enc")
    with pytest.raises(objectstore.ObjectStoreError, match="HTTP 403"):
        _store(fake_s3, secret="wrong").put("backups/x", b"x")        # bad credentials are refused, not ignored
    with pytest.raises(objectstore.ObjectStoreError, match="invalid object key"):
        s.put("../etc/passwd", b"x")


def test_egress_policy_applies_to_the_object_store():
    with pytest.raises(objectstore.ObjectStoreError, match="egress denied"):
        objectstore.ObjectStore("https://ns.compat.objectstorage.uk-london-1.oraclecloud.com", "uk-london-1",
                                "b", "a", "s")                          # not on AAV_EGRESS_ALLOWLIST in tests
    with pytest.raises(objectstore.ObjectStoreError, match="not configured"):
        objectstore.ObjectStore("", "", "", "", "")


def test_admin_store_and_fetch_backup(fake_s3, monkeypatch, capsys):
    from app import admin
    monkeypatch.setattr(objectstore.ObjectStore, "from_env", classmethod(lambda cls: _store(fake_s3)))
    payload = b"Salted__encrypted-dump"
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))
    assert admin.main(["store-backup", "/var/backups/aav/aav-1.dump.enc"]) == 0
    assert '"key": "backups/aav-1.dump.enc"' in capsys.readouterr().out
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))
    assert admin.main(["fetch-backup", "aav-1.dump.enc"]) == 0
    sys.stdout.flush()
    assert out.getvalue() == payload


def test_telemetry_spans_join_incoming_traces_and_skip_probes():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from app import telemetry

    app = FastAPI(version="9.9.9")

    @app.get("/v1/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    mem = InMemorySpanExporter()
    assert telemetry.setup(app, exporter=mem) is True
    c = TestClient(app)
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    c.get("/v1/ping", headers={"traceparent": f"00-{trace_id}-00f067aa0ba902b7-01"})
    c.get("/health")
    server = [s for s in mem.get_finished_spans() if s.kind.name == "SERVER"]
    assert len(server) == 1
    span = server[0]
    assert format(span.context.trace_id, "032x") == trace_id
    assert span.attributes.get("http.route") == "/v1/ping"
    assert span.resource.attributes["service.version"] == "9.9.9"


def test_telemetry_is_off_without_an_endpoint_and_on_with_one():
    code = "import app.main as m; print(m.TELEMETRY_ENABLED)"
    off = subprocess.run([sys.executable, "-c", code], cwd=CP, capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(CP), "OTEL_EXPORTER_OTLP_ENDPOINT": ""})
    on = subprocess.run([sys.executable, "-c", code], cwd=CP, capture_output=True, text=True,
                        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(CP),
                             "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318"})
    assert off.stdout.strip() == "False", off.stderr
    assert on.stdout.strip() == "True", on.stderr
