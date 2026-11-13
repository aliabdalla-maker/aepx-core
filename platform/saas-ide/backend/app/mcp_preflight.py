"""Offline MCP preflight composition; no DB access, HTTP or tool execution.

All trusted_* inputs must be loaded independently from tenant-scoped storage.
This gate is not an atomic dispatch claim and must never authorize side effects
without the separate transactional begin_dispatch() operation.
"""
from .mcp_contract_gate import MCPContractDenied
from .mcp_discovery_policy import authorize_discovered_tool
from .mcp_dispatch_binding import bind_approved_mcp_dispatch
from .mcp_protocol_envelope import build_mcp_tool_call


def prepare_mcp_preflight(*, tenant_id, run_id, approval_id, server_id,
                          tool_name, arguments, discovered_tools,
                          trusted_server_allowlist, trusted_tool_allowlist,
                          trusted_approval, trusted_execution,
                          request_id, client_name, client_version):
    """Compose discovery, approval and canonical request validation fail-closed."""
    authorized = authorize_discovered_tool(
        server_id=server_id, tool_name=tool_name,
        discovered_tools=discovered_tools,
        trusted_server_allowlist=trusted_server_allowlist,
        trusted_tool_allowlist=trusted_tool_allowlist)
    if authorized["server_id"] != server_id or authorized["tool_name"] != tool_name:
        raise MCPContractDenied("MCP discovery mismatch")
    bound = bind_approved_mcp_dispatch(
        tenant_id=tenant_id, run_id=run_id, approval_id=approval_id,
        tool_name=tool_name, arguments=arguments,
        allowed_tools=trusted_tool_allowlist[server_id],
        trusted_approval=trusted_approval, trusted_execution=trusted_execution)
    envelope = build_mcp_tool_call(
        bound_call=bound, request_id=request_id,
        client_name=client_name, client_version=client_version)
    return {"tenant_id": tenant_id, "run_id": run_id,
            "approval_id": approval_id, "server_id": server_id,
            "idempotency_key": bound["idempotency_key"],
            "envelope": envelope}
