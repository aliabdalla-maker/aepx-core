import pytest

from aepx import AepxClient

DID = "did:key:z6MkTESTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DOC = {"id": DID, "verificationMethod": []}


def test_did_create_and_resolve(fake_api):
    fake_api.on("POST", "/did", body={"did": DID, "did_document": DOC, "private_key_hex": "ab" * 32})
    fake_api.on("GET", f"/did/{DID}", body=DOC)
    client = AepxClient()
    created = client.did.create()
    assert created["did"] == DID
    assert client.did.resolve(DID) == DOC


def test_did_resolve_malformed_raises_value_error(fake_api):
    fake_api.on("GET", "/did/", status=400, body={"detail": "unsupported DID method"})
    with pytest.raises(ValueError, match="unsupported DID method"):
        AepxClient().did.resolve("not-a-did")


def test_connectors_list(fake_api):
    fake_api.on("GET", "/health", body={
        "connector_count": 107, "categories": ["blockchain"], "connectors": ["ethereum"]})
    listing = AepxClient().connectors.list()
    assert listing["connector_count"] == 107
    assert "blockchain" in listing["categories"]


def test_connectors_invoke_success(fake_api):
    fake_api.on("POST", "/bus/route", body={"connector": "ml", "maturity": "specialized", "response": {}})
    result = AepxClient().connectors.invoke("ml", {"op": "ping"})
    assert result["status"] == 200
    assert result["connector"] == "ml"


def test_connectors_invoke_denial_is_a_result_not_an_exception(fake_api):
    fake_api.on("POST", "/bus/route", status=403, body={"detail": "policy denies risk level AIA-R3"})
    result = AepxClient().connectors.invoke("opcua", {"op": "read_tag"})
    assert result["status"] == 403
    assert result["denied"] is True
    assert "policy denies" in result["reason"]


def test_trust_get_and_adjust(fake_api):
    fake_api.on("GET", "/trust/agent-1", body={"entity_id": "agent-1", "trust_score": 50, "level": "Provisional"})
    fake_api.on("POST", "/trust/agent-1/adjust", body={"entity_id": "agent-1", "behaviour_score": 60})
    client = AepxClient()
    assert client.trust.get("agent-1")["trust_score"] == 50
    assert client.trust.adjust("agent-1", "behaviour", 10)["behaviour_score"] == 60


def test_ledger_anchors_and_verify(fake_api):
    fake_api.on("GET", "/ledger/anchors", body=[{"seq_no": 1, "anchor_hash": "aa"}])
    fake_api.on("GET", "/ledger/verify/7", body={"audit_id": 7, "anchored": True, "chain_valid": True})
    client = AepxClient()
    assert client.ledger.anchors()[0]["seq_no"] == 1
    assert client.ledger.verify(7)["chain_valid"] is True


def test_audit_tail_and_policy(fake_api):
    fake_api.on("GET", "/audit", body=[{"topic": "connector.invoked", "event": {}}])
    fake_api.on("POST", "/policy/evaluate", body={"risk_level": "S1", "allowed": True, "max_risk_level": "S2"})
    client = AepxClient()
    assert client.audit.tail()[0]["topic"] == "connector.invoked"
    assert client.audit.policy("S1")["allowed"] is True
