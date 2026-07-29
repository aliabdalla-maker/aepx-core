from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.json() == {"status": "ok", "service": "verification"}


def test_verify_bands():
    resp = client.post(
        "/verify",
        json={
            "workflow_id": "wf-1",
            "claims": [
                {"text": "F = ma", "source_ids": ["s1", "s2", "s3"]},
                {"text": "unsupported claim", "source_ids": []},
            ],
        },
    )
    body = resp.json()
    assert body["results"][0]["confidence_band"] == "GREEN"
    assert body["results"][1]["confidence_band"] == "GREY"
