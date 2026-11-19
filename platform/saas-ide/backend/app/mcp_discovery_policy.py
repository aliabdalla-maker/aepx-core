"""Fail-closed MCP discovery policy, offline only.

Discovery data is untrusted. A real client must authenticate the server,
negotiate protocol capabilities and validate the transport separately.
"""
import re
from .mcp_contract_gate import MCPContractDenied

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MAX_TOOLS = 128

def authorize_discovered_tool(*, server_id, tool_name, discovered_tools,
                              trusted_server_allowlist, trusted_tool_allowlist):
    """Require exact server and tool membership and unique discovery names."""
    if (not isinstance(server_id, str) or not _NAME.fullmatch(server_id) or
        not isinstance(tool_name, str) or not _NAME.fullmatch(tool_name) or
        not isinstance(trusted_server_allowlist, (set, frozenset, tuple, list)) or
        server_id not in trusted_server_allowlist or
        not isinstance(trusted_tool_allowlist, dict)):
        raise MCPContractDenied("untrusted MCP server")
    allowed = trusted_tool_allowlist.get(server_id)
    if (not isinstance(allowed, (set, frozenset, tuple, list)) or
        tool_name not in allowed or
        not isinstance(discovered_tools, list) or
        len(discovered_tools) > _MAX_TOOLS):
        raise MCPContractDenied("MCP tool not permitted or discovery invalid")
    seen = set()
    for tool in discovered_tools:
        if not isinstance(tool, dict):
            raise MCPContractDenied("invalid MCP discovery record")
        name = tool.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
            raise MCPContractDenied("duplicate or invalid discovered MCP tool")
        seen.add(name)
    if tool_name not in seen:
        raise MCPContractDenied("approved MCP tool absent from discovery")
    return {"server_id": server_id, "tool_name": tool_name}
