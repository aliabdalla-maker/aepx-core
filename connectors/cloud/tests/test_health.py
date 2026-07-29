import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-cloud"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 10


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/cloudflare", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:cloudflare"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404
