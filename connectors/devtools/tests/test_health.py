import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-devtools"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 11


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/terraform-cloud", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:terraform-cloud"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404


def test_github_adapter_falls_back_without_network(monkeypatch):
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectError("no network in unit tests")

    monkeypatch.setattr(httpx, "get", _boom)
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/github", "payload": {"op": "list_open_issues"}},
    )
    body = resp.json()
    assert body["maturity"] == "specialized_degraded"
    assert body["source"] == "connector:github"


def test_github_adapter_uses_live_response(monkeypatch):
    import httpx

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {"number": 1, "title": "Real bug", "state": "open"},
                {"number": 2, "title": "A PR", "state": "open", "pull_request": {}},
            ]

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/x", "receiver": "aepx://connector/github",
            "payload": {"op": "list_open_issues", "repo": "octocat/Hello-World"},
        },
    )
    body = resp.json()
    assert body["maturity"] == "specialized"
    assert body["result"] == [{"number": 1, "title": "Real bug", "state": "open"}]  # PR filtered out
