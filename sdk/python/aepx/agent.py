import httpx


class Agent:
    """Per Instructional Manual §3.7 — the `pip install aepx` developer
    experience the source manual repeats verbatim throughout every pass:

        from aepx import Agent
        agent = Agent("tutor")
        response = agent.execute("Explain Newton's Laws")
    """

    def __init__(self, name: str, gateway_url="http://localhost:8000", registry_url="http://localhost:8003"):
        self.name = name
        self.gateway_url = gateway_url
        self.registry_url = registry_url
        self.id = None

    def register(self) -> str:
        resp = httpx.post(f"{self.registry_url}/agents", json={"name": self.name})
        resp.raise_for_status()
        self.id = resp.json()["id"]
        return self.id

    def execute(self, prompt: str, capability: str = "generate") -> dict:
        if not self.id:
            self.register()
        resp = httpx.post(
            f"{self.gateway_url}/execute",
            params={"agent_id": self.id, "capability": capability},
            json={"prompt": prompt},
        )
        resp.raise_for_status()
        return resp.json()
