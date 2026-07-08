from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health").json()
    assert resp["status"] == "ok"
    assert resp["service"] == "governance"
    assert resp["persisted"] is False  # no Postgres in the unit-test environment


def test_policy_allows_below_max_risk():
    resp = client.post("/policy/evaluate", params={"risk_level": "S1"})
    assert resp.json()["allowed"] is True


def test_policy_denies_above_max_risk():
    resp = client.post("/policy/evaluate", params={"risk_level": "S4"})
    assert resp.json()["allowed"] is False


def test_policy_accepts_aia_r_style_labels():
    resp = client.post("/policy/evaluate", params={"risk_level": "AIA-R1"})
    assert resp.json()["allowed"] is True


def test_audit_starts_empty():
    assert client.get("/audit").json() == []


def test_record_falls_back_to_memory_without_postgres():
    from app.main import _record

    _record("workflow.completed", {"workflow_id": "abc", "status": "COMPLETED"})
    audit = client.get("/audit").json()
    assert audit[0]["topic"] == "workflow.completed"
    assert audit[0]["event"]["workflow_id"] == "abc"
