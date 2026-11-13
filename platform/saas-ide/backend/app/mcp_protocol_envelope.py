"""Offline MCP 2026-07-28 JSON-RPC tool-call envelope.

Pure serialization only. Does not authenticate endpoints, send HTTP, discover
tools or authorize a dispatch. Only trusted upstream code may supply a bound call.
"""
import json
from .mcp_contract_gate import MCPContractDenied

PROTOCOL_VERSION = "2026-07-28"

def build_mcp_tool_call(*, bound_call, request_id, client_name, client_version):
    """Create stateless MCP tool call payload and matching routing headers."""
    if not isinstance(bound_call, dict):
        raise MCPContractDenied("bound tool call required")
    name = bound_call.get("tool_name")
    payload = bound_call.get("arguments_json")
    if (not isinstance(name, str) or not name or
        not isinstance(payload, str) or len(payload.encode("utf-8")) > 65536 or
        not isinstance(request_id, (str, int)) or isinstance(request_id, bool) or
        not str(request_id) or
        not isinstance(client_name, str) or not 1 <= len(client_name) <= 128 or
        not isinstance(client_version, str) or not 1 <= len(client_version) <= 64):
        raise MCPContractDenied("invalid MCP envelope input")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in name + client_name + client_version):
        raise MCPContractDenied("unsafe MCP header or client metadata")
    try:
        arguments = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise MCPContractDenied("invalid bound JSON arguments") from exc
    if not isinstance(arguments, dict):
        raise MCPContractDenied("MCP arguments must be an object")
    return {
        "headers": {"MCP-Protocol-Version": PROTOCOL_VERSION,
                    "Mcp-Method": "tools/call", "Mcp-Name": name},
        "jsonrpc": {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments,
                               "_meta": {"io.modelcontextprotocol/clientInfo":
                                         {"name": client_name, "version": client_version}}}},
    }
