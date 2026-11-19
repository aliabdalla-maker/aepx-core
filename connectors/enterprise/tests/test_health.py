import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-enterprise"
    assert body["domains"] == ["hrm", "scm"]


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 14


def test_domains_are_first_class_resources():
    body = client.get("/domains").json()
    names = {domain["name"] for domain in body["domains"]}
    assert names == {"scm", "hrm"}

    scm = client.get("/domains/scm").json()
    assert "inventory.read" in scm["capabilities"]
    assert "purchase_order.approve" in scm["approval_required"]

    hrm = client.get("/domains/hrm").json()
    assert "workday" in hrm["connectors"]
    assert "termination.approve" in hrm["approval_required"]
    assert "special-category" in hrm["data_classes"]


def test_domain_connector_availability():
    body = client.get("/domains/hrm/connectors").json()
    assert body["domain"] == "hrm"
    assert set(body["connectors"]) == {"workday", "bamboohr", "successfactors", "sap"}
    assert body["unavailable"] == []


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/zoho-crm", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:zoho-crm"


def test_domain_bound_dispatch():
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/supply-planner",
            "receiver": "aepx://connector/sap",
            "payload": {"op": "inventory.read"},
            "metadata": {"domain": "scm"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "scm"
    assert "scm" in body["domains"]


def test_cross_domain_dispatch_rejected():
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/hr",
            "receiver": "aepx://connector/zoho-crm",
            "payload": {"op": "worker.read"},
            "metadata": {"domain": "hrm"},
        },
    )
    assert resp.status_code == 400


def test_unknown_domain_404():
    assert client.get("/domains/unknown").status_code == 404


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404
