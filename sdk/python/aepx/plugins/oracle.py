"""RFC-0008 chain->AI oracle bridge — SDK wrapper.

Drives the off-chain decision pipeline (governed AI call + Verification
scoring) exposed by services/oracle-bridge, and lets an operator trigger an
on-chain poll cycle. The on-chain request itself is made *from a contract*
(AEPXOracle.sol's requestDecision); this plugin is the off-chain side an
agent or operator talks to.
"""
from aepx.plugins.base import AepxPlugin


class OraclePlugin(AepxPlugin):
    name = "oracle"

    def __init__(self, oracle_url: str = "http://localhost:8015"):
        self.oracle_url = oracle_url.rstrip("/")

    def decide(self, prompt: str, request_id: int | None = None) -> dict:
        """Run the chain->AI pipeline off-chain: a governed AI call scored by
        the Verification Engine. Returns {answer, confidence, band, ...}. Works
        with no chain configured — this is the always-on path."""
        body = {"prompt": prompt}
        if request_id is not None:
            body["request_id"] = request_id
        resp = self._post(f"{self.oracle_url}/oracle/decide", json=body)
        resp.raise_for_status()
        return resp.json()

    def poll(self) -> dict:
        """Trigger one on-chain poll cycle (fulfil any pending AEPXOracle
        requests). A no-op summary when no chain is configured."""
        resp = self._post(f"{self.oracle_url}/oracle/poll")
        resp.raise_for_status()
        return resp.json()

    def history(self, limit: int = 50) -> list:
        resp = self._get(f"{self.oracle_url}/oracle/history", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()
