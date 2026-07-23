from fastapi.testclient import TestClient

import app.main as bridge
from app.main import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "oracle-bridge"
    # No ORACLE_* env in the unit-test environment — the on-chain listener
    # must be idle, and the off-chain pipeline must still be available.
    assert body["chain_configured"] is False


def test_decide_degrades_clean_when_downstreams_unreachable():
    # No Connector Bus or Verification Engine running in unit tests — the
    # decision must still come back well-formed (band GREY, confidence 0),
    # never a 5xx (RFC-0008 §3 degrade-clean discipline).
    resp = client.post("/oracle/decide", json={"prompt": "Is 2+2=4?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["band"] == "GREY"
    assert body["confidence"] == 0
    assert body["prompt"] == "Is 2+2=4?"
    assert body["reason"]  # a concrete degrade reason, not silent


def test_decide_happy_path(monkeypatch):
    # Simulate a reachable governed AI call + a Verification score, so the
    # full chain→AI pipeline (governed answer -> evidence score -> scored
    # decision) is exercised without real infra.
    monkeypatch.setattr(bridge, "_governed_ai_call",
                        lambda prompt: ("4", "connector:ml", None))
    monkeypatch.setattr(bridge, "_verify",
                        lambda answer, source, rid: (90, "GREEN", None))
    resp = client.post("/oracle/decide", json={"prompt": "What is 2+2?", "request_id": 7})
    body = resp.json()
    assert body["answer"] == "4"
    assert body["confidence"] == 90
    assert body["band"] == "GREEN"
    assert body["request_id"] == 7


def test_poll_noop_without_chain():
    body = client.post("/oracle/poll").json()
    assert body["chain_configured"] is False
    assert body["processed"] == 0


def test_history_records_decisions():
    client.post("/oracle/decide", json={"prompt": "remember me"})
    history = client.get("/oracle/history").json()
    assert any(d["prompt"] == "remember me" for d in history)
