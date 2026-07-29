from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "identity"}


def test_issue_token():
    resp = client.post("/token", params={"subject": "tutor-agent"})
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
