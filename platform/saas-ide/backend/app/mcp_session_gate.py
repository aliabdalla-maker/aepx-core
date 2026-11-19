"""Pure offline MCP session-state gate; no transport, credentials or execution."""
from dataclasses import dataclass
from .mcp_contract_gate import MCPContractDenied
from .mcp_initialized_gate import validate_mcp_initialized_notification

@dataclass(frozen=True)
class SessionState:
    phase: str = "new"
    version: str = ""
    server_name: str = ""

def accept_initialize(state, *, negotiated_version, expected_version,
                      server_name, approved_server_name):
    if not isinstance(state, SessionState) or state.phase != "new":
        raise MCPContractDenied("initialize out of order")
    if not all(isinstance(v, str) and v for v in
               (negotiated_version, expected_version, server_name, approved_server_name)):
        raise MCPContractDenied("missing initialization binding")
    if negotiated_version != expected_version or server_name != approved_server_name:
        raise MCPContractDenied("initialization binding mismatch")
    return SessionState("initialized_response_validated", negotiated_version, server_name)

def accept_initialized(state, *, body, expected_version):
    if not isinstance(state, SessionState) or state.phase != "initialized_response_validated":
        raise MCPContractDenied("initialized notification out of order")
    validate_mcp_initialized_notification(
        body=body, initialized_version=state.version, expected_version=expected_version)
    return SessionState("offline_contract_complete", state.version, state.server_name)

def require_authenticated_transport(state, *, tls_identity_verified=False,
                                    token_audience_verified=False,
                                    resource_authorized=False):
    if state.phase != "offline_contract_complete" or not (
        tls_identity_verified and token_audience_verified and resource_authorized
    ):
        raise MCPContractDenied("authenticated MCP transport not established")
    # Boolean flags alone are NOT evidence of authentication. The caller must
    # supply verified assertions from a trusted gateway; no tool execution here.
    return SessionState("gateway_assertions_supplied", state.version, state.server_name)
