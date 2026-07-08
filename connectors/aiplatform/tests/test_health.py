import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-aiplatform"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 14


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/deepseek", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:deepseek"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404


def test_ml_adapter_falls_back_when_ollama_unreachable():
    # No Ollama running in the unit-test environment — the adapter must
    # degrade gracefully, not raise.
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/ml", "payload": {"prompt": "hello"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["maturity"] == "specialized_degraded"
    assert body["source"] == "connector:ml"


def test_ml_adapter_uses_live_response_when_ollama_reachable(monkeypatch):
    from app.adapters import SPECIALIZED

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "F = ma"}

    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResp())
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/ml", "payload": {"prompt": "Newton's second law"}},
    )
    body = resp.json()
    assert body["maturity"] == "specialized"
    assert body["result"] == "F = ma"
