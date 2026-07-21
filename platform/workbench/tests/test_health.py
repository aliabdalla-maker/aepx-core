from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "workbench"


def test_unreachable_backing_service_is_502_not_500():
    # No live services in the unit-test environment — every proxy endpoint
    # must degrade to a clean 502 with a reason, never a raw 500.
    for path in ("/api/connectors", "/api/trust/some-agent", "/api/ledger/anchors",
                 "/api/audit", "/api/agents"):
        resp = client.get(path)
        assert resp.status_code == 502, f"{path} returned {resp.status_code}"
        assert "unreachable" in resp.json()["detail"]


def test_invoke_unreachable_bus_is_502():
    resp = client.post("/api/invoke", json={"connector": "ml", "payload": {"op": "ping"}})
    assert resp.status_code == 502


def test_did_create_unreachable_identity_is_502():
    assert client.post("/api/did").status_code == 502


def test_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Workbench" in resp.text
