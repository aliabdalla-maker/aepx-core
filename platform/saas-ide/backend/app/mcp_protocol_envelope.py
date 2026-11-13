"""Offline MCP 2026-07-28 JSON-RPC tool-call envelope.

Pure serialization only. Does not authenticate endpoints, send HTTP, discover
tools or authorize a dispatch. Only trusted upstream code may supply a bound call.
"""
import json
import hashlib
import re
from .mcp_contract_gate import MCPContractDenied

PROTOCOL_VERSION = "2026-07-28"

def build_mcp_tool_call(*, bound_call, request_id, client_name, client_version):
    """Create stateless MCP tool call payload and matching routing headers."""
    if not isinstance(bound_call, dict):
        raise MCPContractDenied("bound tool call required")
    name = bound_call.get("tool_name")
    payload = bound_call.get("arguments_json")
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) or
        not isinstance(payload, str) or len(payload.encode("utf-8")) > 65536 or
        not isinstance(request_id, (str, int)) or isinstance(request_id, bool) or
        not str(request_id) or
        not isinstance(client_name, str) or not 1 <= len(client_name) <= 128 or
        not isinstance(client_version, str) or not 1 <= len(client_version) <= 64):
        raise MCPContractDenied("invalid MCP envelope input")
    if (type(request_id) is int and not -(2**53) < request_id < 2**53) or (type(request_id) is str and (not request_id or len(request_id) > 128 or any(ord(ch) < 33 or ord(ch) > 126 for ch in request_id))):
        raise MCPContractDenied("unsafe JSON-RPC request ID")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in name + client_name + client_version):
        raise MCPContractDenied("unsafe MCP header or client metadata")
    try:
        arguments = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise MCPContractDenied("invalid bound JSON arguments") from exc
    if not isinstance(arguments, dict):
        raise MCPContractDenied("MCP arguments must be an object")
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    if (canonical != payload or
        hashlib.sha256(payload.encode("utf-8")).hexdigest() != bound_call.get("arguments_sha256")):
        raise MCPContractDenied("MCP bound argument integrity mismatch")
    return {
        "headers": {"Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": PROTOCOL_VERSION,
                    "Mcp-Method": "tools/call", "Mcp-Name": name},
        "jsonrpc": {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments,
                               "_meta": {"io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
                                         "io.modelcontextprotocol/clientCapabilities": {},
                                         "io.modelcontextprotocol/clientInfo":
                                         {"name": client_name, "version": client_version}}}},
    }
