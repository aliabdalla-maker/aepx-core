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
