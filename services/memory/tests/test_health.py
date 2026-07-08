from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "memory"}


def test_write_and_read_session():
    client.post("/memory/session", json={"agent_id": "a1", "content": {"turn": "hello"}})
    resp = client.get("/memory/session/a1")
    assert len(resp.json()) == 1
