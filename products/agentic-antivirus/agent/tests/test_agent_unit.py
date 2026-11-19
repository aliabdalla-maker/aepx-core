"""Agent unit tests that run on every target OS in CI (no control plane needed)."""
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[1] / "detection")]

from aav_agent import platform_ops  # noqa: E402
from aav_agent.quarantine import Vault  # noqa: E402
from aav_agent.store import State  # noqa: E402
from aav_agent.trust import Verifier, canonical  # noqa: E402
from aav_detection import Engine  # noqa: E402

BUNDLE = json.loads((HERE.parents[1] / "detection" / "rules" / "baseline.json").read_text())
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}" + "$EICAR-STANDARD-" + "ANTIVIRUS-TEST-FILE!$H+H*").encode()


def test_engine_signature_bytes_and_behaviour():
    e = Engine(BUNDLE["body"], BUNDLE["version"])
    assert e.scan_bytes(EICAR).rule_id == "sig.eicar.sha256"
    assert e.scan_bytes(b"x" * 100 + EICAR).rule_id == "sig.eicar.bytes"
    assert e.scan_bytes(b"ordinary text") is None
    d = e.evaluate_event({"kind": "process_start", "event_uid": "1", "process": "vssadmin.exe",
                          "cmdline": "vssadmin delete shadows /all"})
    assert d[0].rule_id == "beh.ransom.shadow_delete" and d[0].rule_version == "1"


def test_chunk_boundary_byte_match(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"\0" * (1024 * 1024 - 10) + EICAR[:24] + b"tail")
    e2 = Engine({"byte_signatures": [dict(BUNDLE["body"]["byte_signatures"][0], max_offset=1 << 40)]}, "t")
    assert e2.scan_file(str(f))[1] is not None


def test_verifier_rejects_tampering():
    k = Ed25519PrivateKey.generate()
    pem = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    obj = {"a": 1}
    sig = base64.b64encode(k.sign(canonical(obj))).decode()
    v = Verifier(pem)
    assert v.ok(obj, sig) and not v.ok({"a": 2}, sig) and not v.ok(obj, "garbage")


def test_buffer_limit_and_idempotency(tmp_path):
    s = State(tmp_path / "s")
    s.put("policy", {"bundle": {"body": {"event_buffer_mb": 1}}})
    for i in range(2500):
        s.add_event("process_start", {"pid": i, "cmdline": "y" * 600})
    s.add_event("detection", {"rule_id": "x"})
    assert s.buffered_bytes() <= 1024 * 1024
    assert any(b["kind"] == "detection" for _, b in s.pending_events(100000))  # high priority kept
    s.mark_seen("k1", "c1", "acknowledged", {"ok": True})
    s.mark_seen("k1", "c2", "failed", {})
    assert s.seen("k1")["command_id"] == "c1"


def test_vault_encrypts_and_restores_only_clean(tmp_path):
    s = State(tmp_path / "s")
    v = Vault(s)
    e = Engine(BUNDLE["body"], BUNDLE["version"])
    bad = tmp_path / "bad.com"
    bad.write_bytes(EICAR)
    meta = v.quarantine(str(bad), "x", e.scan_bytes(EICAR))
    assert not bad.exists() and EICAR not in (s.root / "quarantine" / f"{meta['local_id']}.bin").read_bytes()
    assert v.restore(meta["local_id"], e)["restored"] is False and not bad.exists()
    ok = tmp_path / "ok.txt"
    ok.write_text("fine")
    m2 = v.quarantine(str(ok), "y", e.scan_bytes(EICAR))
    assert v.restore(m2["local_id"], e)["restored"] is True and ok.read_text() == "fine"


def test_isolation_rules_keep_management_path():
    for system in ("Linux", "Windows", "Darwin"):
        cmds = " ".join(" ".join(c) for c in platform_ops.isolation_commands(system, ["203.0.113.10"]))
        assert "203.0.113.10" in cmds
        assert platform_ops.release_commands(system)


# --- SEC-01 / SEC-05 (deployment prompt §3A): archives, progress, cancellation, time limit, posture -------
def _scan_agent(tmp_path, replies):
    import httpx
    from aav_agent.agent import Agent
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json={"cancel": replies(body, len(sent))})
    a = Agent(str(tmp_path / "state"), http=httpx.Client(base_url="https://console.example.com",
                                                         transport=httpx.MockTransport(handler)))
    a.state.put("identity", {"device_key": "k", "base_url": "https://console.example.com"})
    a._engine = Engine(BUNDLE["body"], BUNDLE["version"])
    return a, sent


def test_archive_members_scanned_and_encrypted_members_reported(tmp_path):
    import io
    import tarfile
    import zipfile
    from aav_agent import agent as agent_mod
    a, sent = _scan_agent(tmp_path, lambda b, n: False)
    d = tmp_path / "files"
    d.mkdir()
    with zipfile.ZipFile(d / "invoice.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("readme.txt", "hello")
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z2:
            z2.writestr("payload.com", EICAR)
        z.writestr("nested.zip", inner.getvalue())
    with zipfile.ZipFile(d / "secret.zip", "w") as z:
        z.writestr("doc.txt", "x")
    raw = bytearray((d / "secret.zip").read_bytes())
    raw[6] |= 0x1                                  # mark the member encrypted (general purpose flag bit 0)
    cd = raw.rfind(b"PK\x01\x02")
    raw[cd + 8] |= 0x1
    (d / "secret.zip").write_bytes(bytes(raw))
    with tarfile.open(d / "logs.tar.gz", "w:gz") as t:
        data = b"plain log line\n"
        info = tarfile.TarInfo("app.log")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    (d / "notes.txt").write_text("nothing here")
    r = a.scan_paths([str(d)], job_group="g1")
    assert r["detections"] == 1 and r["archives"] >= 3, r
    assert r["gaps"].get("encrypted_archive") == 1
    assert r["status"] == "complete"
    events = [e for _, e in a.state.pending_events() if e["kind"] == "archive_member_detected"]
    assert events and "nested.zip!payload.com" in events[0]["data"]["member"]
    assert sent[0]["status"] == "running" and sent[-1]["status"] == "complete"
    assert agent_mod.ARCHIVE_MAX_DEPTH >= 1


def test_scan_cancelled_by_console_and_time_limit(tmp_path, monkeypatch):
    from aav_agent import agent as agent_mod
    monkeypatch.setattr(agent_mod, "PROGRESS_SECONDS", 0.0)
    d = tmp_path / "many"
    d.mkdir()
    for i in range(30):
        (d / f"f{i}.txt").write_text("x" * 100)
    a, sent = _scan_agent(tmp_path, lambda b, n: n >= 3)   # the console asks to stop on the 3rd report
    r = a.scan_paths([str(d)], job_group="g2")
    assert r["status"] == "cancelled" and r["scanned"] < 30 and sent[-1]["status"] == "cancelled"
    a2, _ = _scan_agent(tmp_path / "b", lambda b, n: False)
    ticks = iter(range(10_000))   # a clock that advances 1 s per reading, so the limit trips on any OS
    with monkeypatch.context() as m:
        m.setattr(agent_mod.time, "monotonic", lambda: float(next(ticks)))
        r2 = a2.scan_paths([str(d)], job_group="g3", max_seconds=0.5)
    assert r2["status"] == "timed_out" and r2["gaps"]["timeout"] == 1
    r3 = a2.scan_paths([str(d / "missing")], job_group="g4")
    assert r3["gaps"]["inaccessible"] == 1


def test_posture_probe_is_read_only_and_reports_unknown_as_none():
    p = platform_ops.posture()
    assert set(p) >= {"disk_encryption", "firewall", "os_updates_pending", "os_build"}
    assert all(v is None or isinstance(v, (bool, int, str)) for v in p.values())
