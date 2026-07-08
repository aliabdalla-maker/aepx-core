from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "workflow"}


def test_create_workflow():
    resp = client.post("/workflows", json={"name": "lesson-plan", "steps": []})
    body = resp.json()
    assert body["status"] == "CREATED"
    assert body["name"] == "lesson-plan"
