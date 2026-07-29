import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-productivity"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 11


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/dropbox", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:dropbox"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404


def test_slack_adapter_stub_without_token(monkeypatch):
    from app.adapters import SPECIALIZED

    monkeypatch.setattr(SPECIALIZED["slack"], "token", None)
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/slack", "payload": {"op": "post_message"}},
    )
    body = resp.json()
    assert body["maturity"] == "specialized_degraded"
    assert "no SLACK_BOT_TOKEN" in body["result"]


def test_slack_adapter_posts_when_token_configured(monkeypatch):
    from app.adapters import SPECIALIZED
    import httpx

    monkeypatch.setattr(SPECIALIZED["slack"], "token", "xoxb-fake-token")

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True, "ts": "1234.5678"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp())
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/x", "receiver": "aepx://connector/slack",
            "payload": {"op": "post_message", "channel": "#general", "text": "hello"},
        },
    )
    body = resp.json()
    assert body["maturity"] == "specialized"
    assert body["result"]["posted"] is True
