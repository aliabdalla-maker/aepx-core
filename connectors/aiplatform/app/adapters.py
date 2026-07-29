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


class SelfHostedMLAdapter:
    """Self-hosted open-weights model server (Ollama reference target; vLLM is
    a drop-in alternative) — near-zero marginal cost per call, per Law 5 and
    the "extremely low cost" positioning. Commercial connectors (openai,
    anthropic, ...) stay stubs until usage data shows the local tier needs
    supplementing.

    Falls back to a canonical stub response if Ollama is unreachable or still
    pulling its model — a cold model server must never turn into a 5xx for
    the whole platform; the caller sees maturity="specialized_degraded"
    instead of a hard failure.
    """

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        self.url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "25"))

    def execute(self, payload: dict) -> dict:
        prompt = payload.get("prompt", "")
        try:
            resp = httpx.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "op": "completion",
                "result": data.get("response", ""),
                "source": "connector:ml",
                "model": self.model,
                "confidence": 0.85,
                "estimated_cost": 0.0,  # self-hosted — compute cost only, not metered per token
                "maturity": "specialized",
            }
        except Exception as e:
            return {
                "op": "completion",
                "result": f"[fallback: self-hosted model '{self.model}' unreachable ({type(e).__name__}) — "
                          f"stub completion for prompt of length {len(prompt)}]",
                "source": "connector:ml",
                "model": self.model,
                "confidence": 0.3,
                "estimated_cost": 0.0,
                "maturity": "specialized_degraded",
            }


SPECIALIZED = {"ml": SelfHostedMLAdapter()}
