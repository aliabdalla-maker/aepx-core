from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.json() == {"status": "ok", "service": "ml-integration"}


def test_predict_unknown_model():
    resp = client.post("/predict", json={"model": "not_real", "features": {}})
    assert "error" in resp.json()
