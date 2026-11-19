"""Offline MCP initialization state gate. No sockets, credentials or side effects."""
from .mcp_contract_gate import MCPContractDenied
from .mcp_initialize_gate import validate_mcp_initialize_response
from .mcp_initialized_gate import validate_mcp_initialized_notification

def validate_mcp_handshake(*, initialize_response, initialize_request_id,
                           initialized_notification, client_versions,
                           approved_server_name, approved_protocol_version):
    if not isinstance(approved_server_name,str) or not approved_server_name:
        raise MCPContractDenied("trusted MCP server identity required")
    if (not isinstance(client_versions,(tuple,list,set,frozenset)) or
        not client_versions or len(client_versions)>32 or
        any(not isinstance(v,str) or not v or len(v)>32 for v in client_versions) or
        not isinstance(approved_protocol_version,str) or not approved_protocol_version or
        approved_protocol_version not in client_versions):
        raise MCPContractDenied("trusted MCP protocol version required")
    initialized=validate_mcp_initialize_response(
        response_body=initialize_response,
        expected_request_id=initialize_request_id,
        client_versions=client_versions,
        expected_server_name=approved_server_name,
        require_server_binding=True)
    if initialized["version"] != approved_protocol_version:
        raise MCPContractDenied("MCP handshake protocol version mismatch")
    acknowledged=validate_mcp_initialized_notification(
        body=initialized_notification,
        initialized_version=initialized["version"],
        expected_version=approved_protocol_version)
    return {"server_name":initialized["server_name"],
            "version":acknowledged["version"],
            "transport_profile":initialized["transport_profile"],
            "offline_contract_valid":True}
