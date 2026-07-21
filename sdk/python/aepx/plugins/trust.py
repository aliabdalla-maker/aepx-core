"""RFC-0002 trust scores — Trust service wrapper."""
from aepx.plugins.base import AepxPlugin


class TrustPlugin(AepxPlugin):
    name = "trust"

    def get(self, entity_id: str) -> dict:
        """5-component score (identity/behaviour/security/evidence/
        reputation), averaged 0-100, with its RFC-0002 level label.
        Fetch-or-create: a never-seen entity gets the default row."""
        resp = self._get(f"{self.client.trust_url}/trust/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    def adjust(self, entity_id: str, component: str, delta: int) -> dict:
        resp = self._post(
            f"{self.client.trust_url}/trust/{entity_id}/adjust",
            json={"component": component, "delta": delta},
        )
        resp.raise_for_status()
        return resp.json()
