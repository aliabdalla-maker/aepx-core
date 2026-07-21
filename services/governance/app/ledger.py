"""Tamper-evident audit anchoring — RFC-0006.

A local SHA-256 hash chain is the always-available default (zero external
dependency, near-zero cost, per Law 5) — each anchor references the
previous anchor's hash, so tampering with any historical audit_log row
changes every anchor_hash after it, which is the core tamper-evidence
property people mean by "blockchain" even without a distributed network.

An EVM-compatible chain is an optional upgrade: when LEDGER_RPC_URL,
LEDGER_CONTRACT_ADDRESS and LEDGER_PRIVATE_KEY are all configured, the same
Merkle root also gets submitted on-chain (see governance/contracts/
AEPXAnchor.sol) — never required, and any failure here must never break
local anchoring.
"""
import hashlib
import json
import os


def _get_web3():
    # Deliberately lazy, unlike the psycopg/kafka imports elsewhere: web3's
    # import alone costs seconds and ~100MB+ RSS, which a Governance
    # container that never anchors on-chain (the default) must not pay —
    # the v1 test box only has ~600MB-1GB headroom (docker-compose.test.yml).
    try:
        from web3 import Web3
        return Web3
    except Exception:
        return None


GENESIS_HASH = "0" * 64

_ANCHOR_ABI = [{
    "inputs": [{"name": "root", "type": "bytes32"}],
    "name": "anchor",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function",
}]

_POLICY_ABI = [{
    "inputs": [],
    "name": "maxRiskLevel",
    "outputs": [{"name": "", "type": "uint8"}],
    "stateMutability": "view",
    "type": "function",
}]

_RISK_ORDER = ["S0", "S1", "S2", "S3", "S4"]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_hash(audit_id: int, topic: str, event: dict) -> str:
    payload = json.dumps({"id": audit_id, "topic": topic, "event": event}, sort_keys=True, default=str).encode()
    return _sha256_hex(payload)


def merkle_root(hashes: list) -> str:
    if not hashes:
        return GENESIS_HASH
    level = list(hashes)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(_sha256_hex((left + right).encode()))
        level = nxt
    return level[0]


class LocalHashChainAnchor:
    """Pure-stdlib hash chain — always available, no external chain needed."""

    def anchor(self, prev_hash: str, root: str) -> dict:
        anchor_hash = _sha256_hex(f"{prev_hash}:{root}".encode())
        return {"backend": "local-hashchain", "anchor_hash": anchor_hash, "tx_ref": None}


class EVMAnchorClient:
    """Optional upgrade — submits the Merkle root to a deployed
    AEPXAnchor.sol instance. Returns None (never raises) whenever
    unconfigured, web3 isn't importable, or the submission fails for any
    reason — local anchoring must never depend on this succeeding.
    """

    def __init__(self):
        self.rpc_url = os.getenv("LEDGER_RPC_URL")
        self.contract_address = os.getenv("LEDGER_CONTRACT_ADDRESS")
        self.private_key = os.getenv("LEDGER_PRIVATE_KEY")

    def configured(self) -> bool:
        return bool(self.rpc_url and self.contract_address and self.private_key)

    def anchor(self, root: str):
        if not self.configured():
            return None
        Web3 = _get_web3()
        if Web3 is None:
            return None
        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 5}))
            account = w3.eth.account.from_key(self.private_key)
            contract = w3.eth.contract(address=Web3.to_checksum_address(self.contract_address), abi=_ANCHOR_ABI)
            tx = contract.functions.anchor(bytes.fromhex(root)).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            return tx_hash.hex()
        except Exception:
            return None


def read_onchain_max_risk_level():
    """Optional upgrade — reads the current ceiling from a deployed
    AEPXPolicyRegistry.sol instance when LEDGER_RPC_URL +
    POLICY_CONTRACT_ADDRESS are configured. Returns None on any failure or
    when unconfigured; callers must fall back to the in-process seed
    policy in that case.
    """
    rpc_url = os.getenv("LEDGER_RPC_URL")
    contract_address = os.getenv("POLICY_CONTRACT_ADDRESS")
    if not rpc_url or not contract_address:
        return None
    Web3 = _get_web3()
    if Web3 is None:
        return None
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 3}))
        contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=_POLICY_ABI)
        level_idx = contract.functions.maxRiskLevel().call()
        return _RISK_ORDER[level_idx]
    except Exception:
        return None
