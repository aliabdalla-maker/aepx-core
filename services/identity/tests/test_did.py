from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_issue_did_shape():
    body = client.post("/did").json()
    assert body["did"].startswith("did:key:z")
    assert "private_key_hex" in body
    assert body["did_document"]["id"] == body["did"]


def test_create_did_round_trips_through_resolve():
    created = client.post("/did").json()
    resolved = client.get(f"/did/{created['did']}").json()
    assert resolved == created["did_document"]


def test_two_dids_are_different():
    a = client.post("/did").json()
    b = client.post("/did").json()
    assert a["did"] != b["did"]


def test_resolve_malformed_did_is_400_not_500():
    resp = client.get("/did/not-a-did")
    assert resp.status_code == 400


def test_resolve_unsupported_method_is_400():
    resp = client.get("/did/did:ethr:0xabc123")
    assert resp.status_code == 400
