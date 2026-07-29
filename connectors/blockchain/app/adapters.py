"""Adapter registry for this category service.

One coarse-grained service per category, one adapter per external system
(SOA-Architecture.md §3.1). StubAdapter answers for every catalogued
connector that doesn't yet have a specialized implementation — swap a stub
for a real adapter class here when credentials and a sandbox exist; nothing
else (bus, catalogue, compose) needs to change.
"""
import os

import httpx


class StubAdapter:
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category

    def execute(self, payload: dict) -> dict:
        op = payload.get("op", "default")
        return {
            "op": op,
            "result": f"[stub response from connector '{self.name}' ({self.category}) for op '{op}']",
            "source": f"connector:{self.name}",
            "confidence": 0.5,
            "maturity": "stub",
        }


def _get_web3():
    # Lazy, like services/governance/app/ledger.py's _get_web3: web3's import
    # alone costs seconds and ~100MB+ RSS. A blockchain connector doing only
    # raw JSON-RPC reads (the eth_blockNumber path below) must not pay that —
    # only the contract_read / contract_write ops need the ABI codec.
    try:
        from web3 import Web3
        return Web3
    except Exception:
        return None


class EVMRPCAdapter:
    """Generic EVM-compatible adapter (any Ethereum-compatible chain —
    mainnet, a public testnet, Polygon/Base/Avalanche, or a local
    Anvil/Hardhat devnet — all speak the same eth_ JSON-RPC methods, so one
    adapter covers all of them via EVM_RPC_URL). Near-zero marginal cost
    when pointed at a self-hosted devnet, per Law 5 — mirrors the
    aiplatform connector's SelfHostedMLAdapter.

    Three operation modes, dispatched on the payload:

      * raw JSON-RPC (default) — ``{"method": "eth_blockNumber", "params": []}``.
        Pure httpx, no web3 needed.
      * ``{"op": "contract_read", ...}``  — AI→chain read: eth_call a view/pure
        function through the ABI codec (RFC-0008 §4.1).
      * ``{"op": "contract_write", ...}`` — AI→chain write: sign and broadcast
        a state-changing transaction (RFC-0008 §4.1). Needs EVM_PRIVATE_KEY.

    Every mode falls back to a canonical stub-shaped response if the RPC
    endpoint is unreachable/unconfigured, web3 isn't importable, or (for
    writes) no signing key is set — a cold/absent chain must never turn into
    a 5xx for the whole platform; the caller sees
    maturity="specialized_degraded" instead of a hard failure. The
    connector is reached only through the Connector Bus, so every one of
    these calls has already passed the bus's trust + policy + circuit-breaker
    gate (SOA-Architecture.md §3.1) — that is what makes a chain *write* a
    *governed* action rather than a raw key operation.
    """

    def __init__(self):
        self.rpc_url = os.getenv("EVM_RPC_URL", "http://localhost:8545")
        self.timeout = float(os.getenv("EVM_RPC_TIMEOUT", "5"))
        # Optional signing key for contract_write. Never persisted; treated
        # as a production secret if set outside local dev (RFC-0008 §6).
        self.private_key = os.getenv("EVM_PRIVATE_KEY")

    def execute(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "contract_read":
            return self._contract_read(payload)
        if op == "contract_write":
            return self._contract_write(payload)
        return self._raw_rpc(payload)

    # -- raw JSON-RPC (unchanged behaviour) -------------------------------
    def _raw_rpc(self, payload: dict) -> dict:
        method = payload.get("method", "eth_blockNumber")
        params = payload.get("params", [])
        try:
            resp = httpx.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return {
                "op": method,
                "result": data.get("result"),
                "source": "connector:ethereum",
                "rpc_url": self.rpc_url,
                "confidence": 0.9,
                "maturity": "specialized",
            }
        except Exception as e:
            return self._degraded(method, f"EVM RPC endpoint '{self.rpc_url}' unreachable ({type(e).__name__})")

    # -- AI→chain contract read (view/pure, no gas, no key) ---------------
    def _contract_read(self, payload: dict) -> dict:
        address = payload.get("address")
        abi = payload.get("abi")
        function = payload.get("function")
        args = payload.get("args", [])
        if not (address and abi and function):
            return self._degraded("contract_read", "contract_read requires 'address', 'abi', and 'function'")
        Web3 = _get_web3()
        if Web3 is None:
            return self._degraded("contract_read", "web3 not importable")
        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": self.timeout}))
            contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
            result = contract.functions[function](*args).call()
            return {
                "op": "contract_read",
                "result": _jsonable(result),
                "source": "connector:ethereum",
                "contract": address,
                "function": function,
                "rpc_url": self.rpc_url,
                "confidence": 0.9,
                "maturity": "specialized",
            }
        except Exception as e:
            return self._degraded("contract_read", f"read of {function}@{address} failed ({type(e).__name__})")

    # -- AI→chain contract write (state-changing, signed tx) --------------
    def _contract_write(self, payload: dict) -> dict:
        address = payload.get("address")
        abi = payload.get("abi")
        function = payload.get("function")
        args = payload.get("args", [])
        if not (address and abi and function):
            return self._degraded("contract_write", "contract_write requires 'address', 'abi', and 'function'")
        if not self.private_key:
            # A write with no key is not an error to hide — it's a clear,
            # actionable degraded reason, so an agent knows the platform was
            # never configured to sign (RFC-0008 §6).
            return self._degraded("contract_write", "EVM_PRIVATE_KEY unset — signing disabled")
        Web3 = _get_web3()
        if Web3 is None:
            return self._degraded("contract_write", "web3 not importable")
        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": self.timeout}))
            account = w3.eth.account.from_key(self.private_key)
            contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
            tx = contract.functions[function](*args).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            return {
                "op": "contract_write",
                "result": {"tx_hash": tx_hash.hex(), "from": account.address},
                "source": "connector:ethereum",
                "contract": address,
                "function": function,
                "rpc_url": self.rpc_url,
                "confidence": 0.9,
                "maturity": "specialized",
            }
        except Exception as e:
            return self._degraded("contract_write", f"write of {function}@{address} failed ({type(e).__name__})")

    def _degraded(self, op: str, reason: str) -> dict:
        return {
            "op": op,
            "result": f"[fallback: {reason} — stub response for op '{op}']",
            "source": "connector:ethereum",
            "rpc_url": self.rpc_url,
            "confidence": 0.3,
            "maturity": "specialized_degraded",
        }


def _jsonable(value):
    # web3 returns bytes / HexBytes / tuples for some ABI types; make the
    # result JSON-serialisable so the FastAPI response never 500s on encode.
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


SPECIALIZED = {"ethereum": EVMRPCAdapter()}
