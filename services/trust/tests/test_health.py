from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health").json()
    assert resp["status"] == "ok"
    assert resp["service"] == "trust"
    assert resp["persisted"] is False  # no Postgres in the unit-test environment


def test_get_trust_default():
    resp = client.get("/trust/agent-1").json()
    assert resp["trust_score"] == 50
    assert resp["level"] == "Provisional"  # 30-59 band; 60+ is "Verified"
    for c in ["identity_score", "behaviour_score", "security_score", "evidence_score", "reputation_score"]:
        assert resp[c] == 50


def test_adjust_trust_moves_score_and_persists_across_calls():
    client.get("/trust/agent-2")  # fetch-or-create
    adjusted = client.post("/trust/agent-2/adjust", json={"component": "behaviour", "delta": 10}).json()
    assert adjusted["behaviour_score"] == 60
    assert adjusted["trust_score"] == round((50 * 4 + 60) / 5)

    refetched = client.get("/trust/agent-2").json()
    assert refetched["behaviour_score"] == 60


def test_adjust_trust_clamps_to_100():
    client.post("/trust/agent-3/adjust", json={"component": "identity", "delta": 1000})
    resp = client.get("/trust/agent-3").json()
    assert resp["identity_score"] == 100


def test_adjust_unknown_component():
    resp = client.post("/trust/agent-4/adjust", json={"component": "nonsense", "delta": 5}).json()
    assert "error" in resp
