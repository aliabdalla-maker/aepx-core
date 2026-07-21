"""Adapter registry for this category service.

One coarse-grained service per category, one adapter per external system
(SOA-Architecture.md §3.1). StubAdapter answers for every catalogued
connector that doesn't yet have a specialized implementation — swap a stub
for a real adapter class here when credentials and a sandbox exist; nothing
else (bus, catalogue, compose) needs to change.
"""


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


import os
import httpx


class EVMRPCAdapter:
    """Generic EVM-compatible JSON-RPC adapter (any Ethereum-compatible
    chain — mainnet, a public testnet, Polygon/Base/Avalanche, or a local
    Anvil/Hardhat devnet — all speak the same eth_ JSON-RPC methods, so one
    adapter covers all of them via EVM_RPC_URL). Near-zero marginal cost
    when pointed at a self-hosted devnet, per Law 5 — mirrors the
    aiplatform connector's SelfHostedMLAdapter.

    Falls back to a canonical stub response if the RPC endpoint is
    unreachable or unconfigured — a cold/absent chain node must never turn
    into a 5xx for the whole platform; the caller sees
    maturity="specialized_degraded" instead of a hard failure.
    """

    def __init__(self):
        self.rpc_url = os.getenv("EVM_RPC_URL", "http://localhost:8545")
        self.timeout = float(os.getenv("EVM_RPC_TIMEOUT", "5"))

    def execute(self, payload: dict) -> dict:
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
            return {
                "op": method,
                "result": f"[fallback: EVM RPC endpoint '{self.rpc_url}' unreachable ({type(e).__name__}) — "
                          f"stub response for method '{method}']",
                "source": "connector:ethereum",
                "rpc_url": self.rpc_url,
                "confidence": 0.3,
                "maturity": "specialized_degraded",
            }


SPECIALIZED = {"ethereum": EVMRPCAdapter()}
