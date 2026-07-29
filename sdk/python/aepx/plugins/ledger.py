"""RFC-0006 tamper-evident audit anchoring — Governance ledger wrapper."""
from aepx.plugins.base import AepxPlugin


class LedgerPlugin(AepxPlugin):
    name = "ledger"

    def anchors(self, limit: int = 50) -> list:
        resp = self._get(f"{self.client.governance_url}/ledger/anchors", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def verify(self, audit_id: int) -> dict:
        """Replays the hash chain from genesis — returns anchored /
        chain_valid / the covering anchor. chain_valid=False means the
        audit history was altered after it was anchored."""
        resp = self._get(f"{self.client.governance_url}/ledger/verify/{audit_id}")
        resp.raise_for_status()
        return resp.json()
