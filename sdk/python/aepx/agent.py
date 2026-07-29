from aepx.client import AepxClient


class Agent:
    """Per Instructional Manual §3.7 — the `pip install aepx` developer
    experience the source manual repeats verbatim throughout every pass:

        from aepx import Agent
        agent = Agent("tutor")
        response = agent.execute("Explain Newton's Laws")

    Backed by AepxClient (client.py) — reach the full protocol surface
    (plugins: did, connectors, trust, ledger, audit) via `agent.client`.
    """

    def __init__(self, name: str, gateway_url="http://localhost:8000", registry_url="http://localhost:8003",
                 did: str | None = None, client: AepxClient | None = None):
        self.name = name
        self.client = client or AepxClient(gateway_url=gateway_url, registry_url=registry_url)
        self.gateway_url = self.client.gateway_url
        self.registry_url = self.client.registry_url
        self.id = None
        # RFC-0006: pass an existing did:key to register under it, or leave
        # None and the Registry mints one (surfaced back here after register()).
        self.did = did

    def register(self) -> str:
        resp = self.client._request(
            "POST", f"{self.registry_url}/agents", json={"name": self.name, "did": self.did}
        )
        resp.raise_for_status()
        body = resp.json()
        self.id = body["id"]
        self.did = body.get("did")
        return self.id

    def execute(self, prompt: str, capability: str = "generate") -> dict:
        if not self.id:
            self.register()
        resp = self.client._request(
            "POST",
            f"{self.gateway_url}/execute",
            params={"agent_id": self.id, "capability": capability},
            json={"prompt": prompt},
        )
        resp.raise_for_status()
        return resp.json()
