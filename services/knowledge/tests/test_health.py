from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "knowledge"}


def test_create_and_search():
    created = client.post(
        "/knowledge",
        json={"title": "Newton's Laws", "content": "F = ma", "source": "physics-101"},
    ).json()
    assert created["id"]

    results = client.post("/knowledge/search", params={"query": "ma"}).json()
    assert any(r["id"] == created["id"] for r in results["results"])
