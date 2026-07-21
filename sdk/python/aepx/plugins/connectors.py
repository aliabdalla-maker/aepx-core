"""Connector catalogue + invocation via the Connector Bus (SOA layer)."""
from aepx.plugins.base import AepxPlugin


class ConnectorsPlugin(AepxPlugin):
    name = "connectors"

    def list(self) -> dict:
        """The live catalogue as the bus sees it — count, categories, names."""
        resp = self._get(f"{self.client.bus_url}/health")
        resp.raise_for_status()
        body = resp.json()
        return {
            "connector_count": body.get("connector_count", 0),
            "categories": body.get("categories", []),
            "connectors": body.get("connectors", []),
        }

    def invoke(self, name: str, payload: dict, sender: str = "aepx://agent/sdk") -> dict:
        """Routes an RFC-0001 envelope to a connector through the full
        trust -> policy -> circuit-breaker chain. A denial comes back as a
        result dict (status + reason), not an exception — a 403 is a
        protocol outcome, not a transport failure."""
        envelope = self.client.envelope(sender, f"aepx://connector/{name}", payload)
        resp = self.client.send(envelope)
        if resp.status_code == 200:
            return {"status": 200, **resp.json()}
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = resp.text
        return {"status": resp.status_code, "denied": resp.status_code in (403, 503), "reason": detail}
