"""did:key decentralized identity (RFC-0006) — Identity service wrapper."""
from aepx.plugins.base import AepxPlugin


class DIDPlugin(AepxPlugin):
    name = "did"

    def create(self) -> dict:
        """Mints a fresh did:key. The private key in the response is
        returned exactly once and never persisted server-side — the caller
        owns safekeeping it."""
        resp = self._post(f"{self.client.identity_url}/did")
        resp.raise_for_status()
        return resp.json()

    def resolve(self, did: str) -> dict:
        """Resolves a did:key into its W3C DID Document (pure decode — no
        registry or chain lookup). Raises ValueError on a malformed DID."""
        resp = self._get(f"{self.client.identity_url}/did/{did}")
        if resp.status_code == 400:
            raise ValueError(resp.json().get("detail", "malformed DID"))
        resp.raise_for_status()
        return resp.json()
