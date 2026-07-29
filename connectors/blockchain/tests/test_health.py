import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "catalogue.json")

from fastapi.testclient import TestClient
from app.main import app, MY_CONNECTORS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "connector-blockchain"


def test_catalogue_loaded():
    assert len(MY_CONNECTORS) == 7


def test_stub_dispatch():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/bitcoin", "payload": {"op": "ping"}},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "connector:bitcoin"
    assert resp.json()["maturity"] == "stub"


def test_unknown_connector_404():
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/not-a-real-one", "payload": {}},
    )
    assert resp.status_code == 404


def test_ethereum_specialized_degrades_without_rpc():
    # No EVM RPC endpoint is running in the unit-test environment — this
    # must degrade to a clean stub-shaped response, never a 5xx (mirrors
    # the aiplatform connector's SelfHostedMLAdapter fallback test).
    resp = client.post(
        "/connector/execute",
        json={"sender": "aepx://agent/x", "receiver": "aepx://connector/ethereum", "payload": {"method": "eth_blockNumber"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "connector:ethereum"
    assert body["maturity"] == "specialized_degraded"


# -- RFC-0008 AI→chain contract read/write (degrade-clean) ----------------

_ERC20_BALANCE_ABI = [{
    "constant": True,
    "inputs": [{"name": "who", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "", "type": "uint256"}],
    "type": "function",
}]


def test_contract_read_degrades_without_rpc():
    # AI→chain read with no chain reachable — never a 5xx, always the
    # canonical specialized_degraded shape (RFC-0008 §4.1).
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/x",
            "receiver": "aepx://connector/ethereum",
            "payload": {
                "op": "contract_read",
                "address": "0x0000000000000000000000000000000000000000",
                "abi": _ERC20_BALANCE_ABI,
                "function": "balanceOf",
                "args": ["0x0000000000000000000000000000000000000000"],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["op"] == "contract_read"
    assert body["source"] == "connector:ethereum"
    assert body["maturity"] == "specialized_degraded"


def test_contract_read_missing_args_degrades():
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/x",
            "receiver": "aepx://connector/ethereum",
            "payload": {"op": "contract_read", "address": "0xabc"},  # no abi/function
        },
    )
    assert resp.status_code == 200
    assert resp.json()["maturity"] == "specialized_degraded"


def test_contract_write_without_key_degrades_clearly():
    # No EVM_PRIVATE_KEY in the test env: a write must degrade with a clear
    # reason (signing disabled), never sign or 5xx (RFC-0008 §6).
    resp = client.post(
        "/connector/execute",
        json={
            "sender": "aepx://agent/x",
            "receiver": "aepx://connector/ethereum",
            "payload": {
                "op": "contract_write",
                "address": "0x0000000000000000000000000000000000000000",
                "abi": _ERC20_BALANCE_ABI,
                "function": "balanceOf",
                "args": ["0x0000000000000000000000000000000000000000"],
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["op"] == "contract_write"
    assert body["maturity"] == "specialized_degraded"
    assert "signing disabled" in body["result"]
