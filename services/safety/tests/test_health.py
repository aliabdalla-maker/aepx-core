from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "safety"}


def test_validate_unverified_without_evidence():
    resp = client.post("/safety/validate", json={"answer": "the sky is green", "evidence": []})
    assert resp.json()["verification_status"] == "Unverified"


def test_validate_verified_with_evidence():
    resp = client.post("/safety/validate", json={"answer": "F=ma", "evidence": ["s1", "s2", "s3"]})
    assert resp.json()["verification_status"] == "Verified"
