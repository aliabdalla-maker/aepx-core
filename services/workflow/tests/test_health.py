from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "workflow"}


def test_create_workflow():
    step = {"capability": "metadata.lookup", "agent_id": "agent-1", "risk_level": "S0"}
    resp = client.post("/workflows", json={"name": "lesson-plan", "steps": [step]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "CREATED"
    assert body["name"] == "lesson-plan"


def test_empty_workflow_rejected():
    # A workflow must declare at least one step (WorkflowIn.steps min_length=1).
    assert client.post("/workflows", json={"name": "empty", "steps": []}).status_code == 422


def test_high_risk_step_requires_governed_approval():
    step = {"capability": "deploy", "agent_id": "agent-1", "risk_level": "S4"}
    assert client.post("/workflows", json={"name": "risky", "steps": [step]}).status_code == 403
