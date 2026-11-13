"""Offline, pure MCP tool-call contract validation.

No network, SDK calls, tool discovery or side effects. The authenticated
adapter must independently verify approval and transport before dispatch.
"""
import hashlib
import json
import re

class MCPContractDenied(ValueError):
    pass

_TOOL = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARGS_BYTES = 65536

def canonical_tool_call(*, tool_name, arguments, allowed_tools,
                        approved_tool, approved_arguments_sha256,
                        idempotency_key):
    """Return an immutable canonical call only for an exact approved payload."""
    if (not isinstance(tool_name, str) or not _TOOL.fullmatch(tool_name) or
        not isinstance(approved_tool, str) or tool_name != approved_tool or
        not isinstance(allowed_tools, (frozenset, set, tuple, list)) or
        tool_name not in allowed_tools):
        raise MCPContractDenied("tool not allowlisted and exactly approved")
    if (not isinstance(arguments, dict) or
        not isinstance(approved_arguments_sha256, str) or
        not _HEX.fullmatch(approved_arguments_sha256) or
        not isinstance(idempotency_key, str) or
        not 1 <= len(idempotency_key) <= 128 or
        any(ord(ch) < 33 or ord(ch) > 126 for ch in idempotency_key)):
        raise MCPContractDenied("invalid arguments, approval digest or idempotency key")
    try:
        payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
        encoded = payload.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MCPContractDenied("noncanonical MCP arguments") from exc
    if len(encoded) > _MAX_ARGS_BYTES:
        raise MCPContractDenied("MCP arguments exceed size bound")
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != approved_arguments_sha256:
        raise MCPContractDenied("MCP arguments differ from approved payload")
    return {"tool_name": tool_name, "arguments_json": payload,
            "arguments_sha256": digest, "idempotency_key": idempotency_key}
