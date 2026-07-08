from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health").json()
    assert resp["status"] == "ok"
    assert resp["service"] == "registry"
    # no Postgres in the unit-test environment — must degrade, not crash
    assert resp["persisted"] is False


def test_create_and_get_agent():
    created = client.post("/agents", json={"name": "tutor-agent"}).json()
    assert created["id"]
    fetched = client.get(f"/agents/{created['id']}").json()
    assert fetched["name"] == "tutor-agent"


def test_list_agents_ranked_by_trust():
    client.post("/agents", json={"name": "agent-a"})
    client.post("/agents", json={"name": "agent-b"})
    listing = client.get("/agents").json()
    scores = [a["trust_score"] for a in listing]
    assert scores == sorted(scores, reverse=True)


def test_get_unknown_agent_404():
    resp = client.get("/agents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_get_malformed_agent_id_returns_404_not_500():
    # Regression: a non-UUID id must 404, not throw an unhandled DB error
    resp = client.get("/agents/not-a-real-uuid")
    assert resp.status_code == 404
