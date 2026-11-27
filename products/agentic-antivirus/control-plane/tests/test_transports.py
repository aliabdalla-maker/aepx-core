"""INT-02 transports beyond REST: gRPC push, SQL and IMAP pull. Each ends in the same canonical ingestion as the
webhook (validation, dedup, attribution, incidents, audit)."""
from __future__ import annotations

import json
from email.message import EmailMessage

import grpc
import psycopg
import pytest
from google.protobuf import struct_pb2

from app import transports
from conftest import ADMIN_DSN


def _integration(admin, kind, protocol, name=None, **extra):
    r = admin.post("/v1/integrations", json={"name": name or f"{kind}-{protocol}", "signal_kind": kind,
                                             "protocol": protocol, **extra})
    assert r.status_code == 201, r.text
    body = r.json()
    assert admin.post(f"/v1/integrations/{body['id']}/maturity",
                      json={"maturity": "test_only", "provider": "acme", "evidence": {}}).status_code == 200
    return body


@pytest.fixture(scope="module")
def grpc_port():
    server, port = transports.start_grpc(0)
    yield port
    server.stop(0)


def _submit(port, iid, secret, payload):
    with grpc.insecure_channel(f"127.0.0.1:{port}") as ch:
        call = ch.unary_unary(transports.GRPC_METHOD, request_serializer=struct_pb2.Struct.SerializeToString,
                              response_deserializer=struct_pb2.Struct.FromString)
        req = struct_pb2.Struct()
        req.update(payload)
        return call(req, metadata=[("x-aav-integration-id", iid), ("x-aav-webhook-secret", secret)], timeout=10)


def test_grpc_ingest(new_account, grpc_port):
    admin = new_account("grpc")
    integ = _integration(admin, "identity", "grpc")
    sig = {"external_id": "g-1", "category": "unusual_sign_in", "severity": "high",
           "observed_at": "2026-11-27T03:00:00Z", "user_ref": "bob@corp.example"}
    out = _submit(grpc_port, integ["id"], integ["webhook_secret"], sig)
    assert out["simulation"] is True and out["incident_id"]
    assert _submit(grpc_port, integ["id"], integ["webhook_secret"], sig)["duplicate"] is True
    with pytest.raises(grpc.RpcError) as e:
        _submit(grpc_port, integ["id"], "wrong", sig)
    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    with pytest.raises(grpc.RpcError) as e:
        _submit(grpc_port, integ["id"], integ["webhook_secret"], {**sig, "external_id": "g-2", "category": "nope"})
    assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT


@pytest.fixture(scope="module")
def source_db():
    name = "aav_src_signals"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name}")
        c.execute(f"CREATE DATABASE {name}")
    info = psycopg.conninfo.conninfo_to_dict(ADMIN_DSN)
    info["dbname"] = name
    with psycopg.connect(**info, autocommit=True) as c:
        c.execute("CREATE TABLE fw_events (id serial, kind text, sev text, at timestamptz, src text)")
        c.execute("INSERT INTO fw_events (kind, sev, at, src) VALUES ('port_scan','medium',now(),'10.0.0.5'),"
                  "('lateral_movement','high',now(),'10.0.0.9'),('bogus','high',now(),'x')")
    yield info
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def test_sql_pull_with_cursor(new_account, source_db):
    admin = new_account("sqlpull")
    endpoint = (f"postgresql://{source_db.get('user', 'postgres')}@/{source_db['dbname']}"
                f"?host={source_db.get('host', '/tmp/pg')}&port={source_db.get('port', 5432)}")
    query = ("SELECT lpad(id::text, 8, '0') AS external_id, kind AS category, sev AS severity, at AS observed_at, "
             "src AS device_ip FROM fw_events WHERE lpad(id::text, 8, '0') > %(cursor)s ORDER BY id")
    integ = _integration(admin, "firewall", "sql", endpoint=endpoint, config={"query": query})
    from app.routers import integrations
    import uuid
    r = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False)
    assert r == {**r, "ok": True, "received": 3, "ingested": 2, "rejected": 1}, r
    again = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False)
    assert again["received"] == 0                                    # cursor advanced
    row = [i for i in admin.get("/v1/integrations").json() if i["id"] == integ["id"]][0]
    assert row["last_health"]["ok"] is True
    bad = _integration(admin, "firewall", "sql", name="bad-sql", endpoint=endpoint,
                       config={"query": "DELETE FROM fw_events"})
    res = transports.poll_integration(uuid.UUID(bad["id"]), uuid.UUID(admin.tenant_id), check_egress=False)
    assert res["ok"] is False and "single SELECT" in res["reason"]
    assert integrations is not None


class FakeIMAP:
    """Stands in for imaplib.IMAP4_SSL: the poller's IMAP command sequence and flag handling."""

    def __init__(self, messages):
        self.messages, self.seen, self.log = messages, set(), []

    def login(self, user, pw):
        assert (user, pw) == ("phish@corp.example", "imap-pass")
        self.log.append("LOGIN")

    def select(self, box):
        self.log.append(f"SELECT {box}")

    def uid(self, cmd, *args):
        self.log.append(cmd)
        if cmd == "SEARCH":
            return "OK", [b" ".join(str(i).encode() for i in self.messages if i not in self.seen)]
        if cmd == "FETCH":
            return "OK", [(b"1 (BODY[] {n}", self.messages[int(args[0])]), b")"]
        if cmd == "STORE":
            self.seen.add(int(args[0]))
            return "OK", []

    def logout(self):
        self.log.append("LOGOUT")


def _mail(mid, body):
    m = EmailMessage()
    m["Message-ID"], m["From"], m["Subject"] = mid, "Bob <bob@corp.example>", "Fwd: invoice"
    m["Date"] = "Fri, 27 Nov 2026 03:00:00 +0000"
    m.set_content(body)
    return m.as_bytes()


def test_imap_phishing_mailbox(new_account, baseline_bundle, monkeypatch):
    import uuid
    admin = new_account("imap")
    integ = _integration(admin, "email", "imap", endpoint="imaps://mail.corp.example:993",
                         config={"username": "phish@corp.example"})
    admin.put(f"/v1/integrations/{integ['id']}/secret", json={"value": "imap-pass"})
    import sys
    from aav_detection import Engine
    eng = Engine({"hash_signatures": [], "byte_signatures": [], "behaviour_rules": [],
                  "reputation": {"malicious_domains": ["evil-invoice.example"]}}, "imap-test")
    monkeypatch.setattr(sys.modules["app.detections"], "current_engine", lambda: eng)
    bad_url = "http://evil-invoice.example/pay"
    box = FakeIMAP({1: _mail("<m1@corp>", f"please check {bad_url} now"), 2: _mail("<m2@corp>", "hello, see https://ok.example/")})
    r = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False,
                                    imap_factory=lambda: box)
    assert r["ok"] and r["ingested"] == 2, r
    assert box.seen == {1, 2} and box.log[0] == "LOGIN" and box.log[-1] == "LOGOUT"
    again = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False,
                                        imap_factory=lambda: box)
    assert again["received"] == 0
