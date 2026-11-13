"""Offline fail-closed MCP protocol version negotiation policy.

No network, OAuth, TLS or capability probing. Version evidence MUST come
from an authenticated initialization exchange in the future transport.
"""
import re
from .mcp_contract_gate import MCPContractDenied

_VERSION=re.compile(r"^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
# Explicit tested implementation support, not a claim of protocol-wide support.
SUPPORTED_POST_ONLY=frozenset({"2025-11-25"})

def select_mcp_protocol_version(*, server_version, client_versions,
                                trusted_supported_versions=SUPPORTED_POST_ONLY):
    if (not isinstance(server_version,str) or
        _VERSION.fullmatch(server_version) is None or
        not isinstance(client_versions,(tuple,list,frozenset,set)) or
        not isinstance(trusted_supported_versions,(tuple,list,frozenset,set)) or
        not client_versions or not trusted_supported_versions):
        raise MCPContractDenied("invalid MCP version negotiation inputs")
    for versions in (client_versions,trusted_supported_versions):
        if (len(versions)>16 or
            any(not isinstance(v,str) or _VERSION.fullmatch(v) is None
                for v in versions)):
            raise MCPContractDenied("invalid MCP version allowlist")
    if server_version not in client_versions or server_version not in trusted_supported_versions:
        raise MCPContractDenied("unsupported or downgraded MCP protocol version")
    return {"version":server_version,"transport_profile":"restricted-post-only",
            "supports_get":False,"supports_sessions":False,"supports_resume":False}
