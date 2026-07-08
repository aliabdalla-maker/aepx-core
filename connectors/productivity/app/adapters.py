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


class SlackAdapter:
    """Posts via Slack's Web API (chat.postMessage) when SLACK_BOT_TOKEN is
    set in Vault/env. With no token configured, returns a canonical stub —
    the honest default for a fresh deployment with no Slack workspace
    connected yet, rather than pretending to have posted."""

    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")

    def execute(self, payload: dict) -> dict:
        op = payload.get("op")
        if op != "post_message":
            return {"op": op, "error": "unsupported operation in this adapter"}

        channel = payload.get("channel", "#general")
        if not self.token:
            return {
                "op": op,
                "result": f"[stub: no SLACK_BOT_TOKEN configured — would post to '{channel}']",
                "source": "connector:slack",
                "confidence": 0.5,
                "maturity": "specialized_degraded",
            }
        try:
            resp = httpx.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"channel": channel, "text": payload.get("text", "")},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "unknown Slack API error"))
            return {
                "op": op,
                "result": {"channel": channel, "posted": True, "ts": data.get("ts")},
                "source": "connector:slack",
                "confidence": 0.99,
                "maturity": "specialized",
            }
        except Exception as e:
            return {
                "op": op,
                "result": f"[fallback: Slack API call failed ({type(e).__name__}) for '{channel}']",
                "source": "connector:slack",
                "confidence": 0.3,
                "maturity": "specialized_degraded",
            }


SPECIALIZED = {"slack": SlackAdapter()}
