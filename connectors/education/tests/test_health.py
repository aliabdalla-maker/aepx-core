import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-education"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 4


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/google-classroom", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:google-classroom"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404
