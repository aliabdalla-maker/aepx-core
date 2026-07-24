"""Real on-chain integration test for the RFC-0006 / RFC-0008 contracts.

Unlike the services' unit tests (which prove the platform degrades cleanly
with NO chain), this compiles the actual Solidity sources with solc 0.8.24
and deploys+exercises them on an in-memory EVM (py-evm via eth-tester) — so
the contracts and the on-chain bridge logic are verified for real, without
needing Docker or anvil. This is the CI-executable half of the "live
on-chain path" (RFC-0008 §9); the docker-compose.chain.yml anvil overlay is
the same contracts against a persistent devnet.

Run:  python -m pytest tests/test_contracts.py -v
Deps: py-solc-x, eth-tester, py-evm, web3 (see tests/requirements.txt).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

web3 = pytest.importorskip("web3")
pytest.importorskip("solcx")
pytest.importorskip("eth_tester")

from web3 import Web3  # noqa: E402  (must follow importorskip guards)
from web3.providers.eth_tester import EthereumTesterProvider  # noqa: E402

from deploy_contracts import compile_contracts, deploy_all  # noqa: E402  (needs sys.path insert above)


@pytest.fixture(scope="module")
def chain():
    w3 = Web3(EthereumTesterProvider())
    artifacts = compile_contracts()
    deployer = w3.eth.accounts[0]
    addrs = deploy_all(w3, deployer, oracle_addr=deployer)
    return w3, artifacts, addrs, deployer


def _contract(w3, artifacts, addrs, name):
    return w3.eth.contract(address=addrs[name], abi=artifacts[name]["abi"])


def test_all_three_compile_and_deploy(chain):
    _, _, addrs, _ = chain
    assert set(addrs) == {"AEPXAnchor", "AEPXPolicyRegistry", "AEPXOracle"}
    for a in addrs.values():
        assert a and a.startswith("0x") and len(a) == 42


def test_anchor_append_only(chain):
    w3, art, addrs, deployer = chain
    anchor = _contract(w3, art, addrs, "AEPXAnchor")
    assert anchor.functions.anchorCount().call() == 0
    root = b"\x11" * 32
    anchor.functions.anchor(root).transact({"from": deployer})
    assert anchor.functions.anchorCount().call() == 1
    assert anchor.functions.latestRoot().call() == root


def test_oracle_request_fulfil_roundtrip(chain):
    # The core chain->AI path: a request is made on-chain, the authorized
    # oracle (here the deployer, mirroring the oracle-bridge's signer) writes
    # back an evidence-scored answer, and getDecision reflects it.
    w3, art, addrs, deployer = chain
    oracle = _contract(w3, art, addrs, "AEPXOracle")

    tx = oracle.functions.requestDecision("Should settlement proceed?").transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    ev = oracle.events.DecisionRequested().process_receipt(receipt)
    req_id = ev[0]["args"]["requestId"]
    assert oracle.functions.isFulfilled(req_id).call() is False

    oracle.functions.fulfillDecision(req_id, "yes - hash chain valid", 82, "AMBER").transact({"from": deployer})
    d = oracle.functions.getDecision(req_id).call()
    # struct order: requester, prompt, answer, confidence, band, fulfilled, requestedAt, fulfilledAt
    assert d[2] == "yes - hash chain valid"
    assert d[3] == 82
    assert d[4] == "AMBER"
    assert d[5] is True
    assert oracle.functions.isFulfilled(req_id).call() is True


def test_oracle_only_authorized_can_fulfil(chain):
    w3, art, addrs, deployer = chain
    oracle = _contract(w3, art, addrs, "AEPXOracle")
    tx = oracle.functions.requestDecision("q").transact({"from": deployer})
    req_id = oracle.events.DecisionRequested().process_receipt(
        w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["requestId"]
    intruder = w3.eth.accounts[1]
    with pytest.raises(Exception):  # reverts: "not oracle"
        oracle.functions.fulfillDecision(req_id, "forged", 100, "GREEN").transact({"from": intruder})


def test_oracle_no_double_fulfil(chain):
    w3, art, addrs, deployer = chain
    oracle = _contract(w3, art, addrs, "AEPXOracle")
    tx = oracle.functions.requestDecision("q2").transact({"from": deployer})
    req_id = oracle.events.DecisionRequested().process_receipt(
        w3.eth.wait_for_transaction_receipt(tx))[0]["args"]["requestId"]
    oracle.functions.fulfillDecision(req_id, "a", 50, "RED").transact({"from": deployer})
    with pytest.raises(Exception):  # reverts: "already fulfilled"
        oracle.functions.fulfillDecision(req_id, "b", 60, "AMBER").transact({"from": deployer})


def test_policy_registry_ceiling(chain):
    w3, art, addrs, deployer = chain
    policy = _contract(w3, art, addrs, "AEPXPolicyRegistry")
    # default seed is S2 (index 2) per the contract constructor
    assert policy.functions.maxRiskLevel().call() == 2
