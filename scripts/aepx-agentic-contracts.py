#!/usr/bin/env python3
"""Pure, offline safety contracts for future MCP, RAG and HITL adapters.
Not a networked MCP server, vector database or durable approval store.
"""
from dataclasses import dataclass
from typing import Any
import hashlib
import json
import time

class Denied(PermissionError): pass

@dataclass(frozen=True)
class ToolPolicy:
    tool: str
    allowed_roles: frozenset[str]
    max_timeout_seconds: int = 10
    requires_approval: bool = False

def authorize_tool(policy: ToolPolicy, *, tool: str, role: str, timeout_seconds: int, approved: bool = False):
    if tool != policy.tool or role not in policy.allowed_roles:
        raise Denied("tool or role not authorised")
    if timeout_seconds <= 0 or timeout_seconds > policy.max_timeout_seconds:
        raise Denied("tool timeout exceeds policy")
    if policy.requires_approval and not approved:
        raise Denied("explicit approval required")
    return {"authorised": True, "tool": tool, "timeout_seconds": timeout_seconds}

def grounded_answer(answer: str, source_ids: list[str], retrieved: list[dict[str, Any]]):
    """Require at least one real retrieved source; not semantic entailment verification."""
    known={str(x.get("id")) for x in retrieved if x.get("id") and x.get("content")}
    if not answer.strip() or not source_ids or not set(source_ids).issubset(known):
        raise Denied("answer missing verified retrieval identifiers")
    return {"answer": answer, "source_ids": source_ids, "grounding_status": "source_ids_checked_only"}

def approval_fingerprint(action: dict[str, Any]):
    return hashlib.sha256(json.dumps(action,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def check_approval(action: dict[str, Any], approval: dict[str, Any], *, now: float | None = None):
    now=time.time() if now is None else now
    if approval.get("status") != "approved" or not approval.get("approver_id"):
        raise Denied("human approval absent or denied")
    if approval.get("action_hash") != approval_fingerprint(action):
        raise Denied("approved action differs from requested action")
    if not isinstance(approval.get("expires_at"),(int,float)) or now >= approval["expires_at"]:
        raise Denied("approval expired")
    if approval.get("consumed",False):
        raise Denied("approval already consumed")
    return {"authorised": True, "action_hash": approval["action_hash"], "approver_id": approval["approver_id"]}
