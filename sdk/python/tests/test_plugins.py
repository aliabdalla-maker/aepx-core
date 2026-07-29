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


# -- RFC-0008 AI->chain (ChainPlugin over the governed connector path) -----

_ABI = [{"inputs": [], "name": "latestRoot", "outputs": [{"type": "bytes32"}],
         "stateMutability": "view", "type": "function"}]


def test_chain_read_goes_through_governed_bus(fake_api):
    fake_api.on("POST", "/bus/route", body={
        "connector": "ethereum", "maturity": "specialized",
        "response": {"op": "contract_read", "result": "0xabc"}})
    result = AepxClient().chain.read("0x0000000000000000000000000000000000000000", _ABI, "latestRoot")
    assert result["status"] == 200
    assert result["connector"] == "ethereum"
    # The AI->chain call must ride the same /bus/route path as any connector
    # (trust + policy + circuit), carrying the contract_read op.
    method, path, kwargs = fake_api.calls[-1]
    assert (method, path) == ("POST", "/bus/route")
    assert kwargs["json"]["payload"]["op"] == "contract_read"


def test_chain_write_carries_write_op(fake_api):
    fake_api.on("POST", "/bus/route", body={"connector": "ethereum", "response": {"op": "contract_write"}})
    AepxClient().chain.write("0x0000000000000000000000000000000000000000", _ABI, "anchor", ["0xdead"])
    _, _, kwargs = fake_api.calls[-1]
    assert kwargs["json"]["payload"]["op"] == "contract_write"
    assert kwargs["json"]["payload"]["function"] == "anchor"


def test_chain_write_denial_is_a_result_not_an_exception(fake_api):
    # A policy/trust denial on a chain write is a governance outcome, surfaced
    # like any other connector denial (RFC-0008 §4.1).
    fake_api.on("POST", "/bus/route", status=403, body={"detail": "policy denies risk level AIA-R2"})
    result = AepxClient().chain.write("0xabc", _ABI, "anchor")
    assert result["status"] == 403
    assert result["denied"] is True


# -- RFC-0008 chain->AI (OraclePlugin over the oracle-bridge) --------------

def test_oracle_decide(fake_api):
    fake_api.on("POST", "/oracle/decide", body={
        "answer": "4", "confidence": 90, "band": "GREEN", "request_id": 7})
    result = AepxClient().oracle.decide("What is 2+2?", request_id=7)
    assert result["answer"] == "4"
    assert result["band"] == "GREEN"
    _, _, kwargs = fake_api.calls[-1]
    assert kwargs["json"]["prompt"] == "What is 2+2?"
    assert kwargs["json"]["request_id"] == 7


def test_oracle_poll_noop_without_chain(fake_api):
    fake_api.on("POST", "/oracle/poll", body={"chain_configured": False, "processed": 0})
    result = AepxClient().oracle.poll()
    assert result["chain_configured"] is False
    assert result["processed"] == 0
