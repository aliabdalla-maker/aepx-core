"""AEP-X governance adapter (AX-01, AX-06, AX-07, AI-02).

Two independent checks must both allow an action:
  1. the product policy engine (policy.py) - tenant rules, roles, approvals; and
  2. AEP-X Governance (`POST /policy/evaluate?risk_level=S<n>` in services/governance), the
     platform's independent risk ceiling.
Governance unreachable, misconfigured, or returning anything but allowed=true -> deny.
"""
from __future__ import annotations

import httpx

from app.config import settings

_transport: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Test hook: route calls to an in-process AEP-X governance app."""
    global _transport
    _transport = transport


def evaluate(risk_level: str) -> dict:
    if not settings.governance_url and _transport is None:
        return {"allowed": False, "source": "aepx-governance", "reason": "governance not configured (fail closed)"}
    base = settings.governance_url or "http://aepx-governance"
    try:
        with httpx.Client(base_url=base, timeout=settings.governance_timeout_s, transport=_transport) as c:
            r = c.post("/policy/evaluate", params={"risk_level": risk_level})
        if r.status_code != 200:
            return {"allowed": False, "source": "aepx-governance", "reason": f"governance HTTP {r.status_code}"}
        body = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"allowed": False, "source": "aepx-governance", "reason": f"governance unreachable: {type(exc).__name__}"}
    return {"allowed": body.get("allowed") is True, "source": "aepx-governance",
            "max_risk_level": body.get("max_risk_level"), "reason": body.get("reason", "")}
