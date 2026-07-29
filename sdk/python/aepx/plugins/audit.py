"""Law 8 audit trail + policy evaluation — Governance wrapper."""
from aepx.plugins.base import AepxPlugin


class AuditPlugin(AepxPlugin):
    name = "audit"

    def tail(self, limit: int = 50) -> list:
        resp = self._get(f"{self.client.governance_url}/audit", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def policy(self, risk_level: str) -> dict:
        """Evaluates an AIA-R0-R4 / S0-S4 label against the active ceiling
        (seed policy, or the on-chain AEPXPolicyRegistry when configured)."""
        resp = self._post(f"{self.client.governance_url}/policy/evaluate", params={"risk_level": risk_level})
        resp.raise_for_status()
        return resp.json()
