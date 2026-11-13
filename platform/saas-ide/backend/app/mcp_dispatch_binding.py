"""Pure MCP dispatch authorization gate; never invokes a provider.

All approval fields MUST originate from trusted tenant-scoped database records,
not the request payload. A separate transaction must reserve dispatch exactly once.
"""
from .mcp_contract_gate import canonical_tool_call, MCPContractDenied

def bind_approved_mcp_dispatch(*, tenant_id, run_id, approval_id,
                               tool_name, arguments, allowed_tools,
                               trusted_approval, trusted_execution):
    """Bind exact tool contract to an already-consumed approval and reserved execution."""
    if (not isinstance(tenant_id, str) or not tenant_id or
        not isinstance(run_id, str) or not run_id or
        not isinstance(approval_id, str) or not approval_id or
        not isinstance(trusted_approval, dict) or
        not isinstance(trusted_execution, dict)):
        raise MCPContractDenied("trusted tenant/run/approval evidence required")
    if (trusted_approval.get("tenant_id") != tenant_id or
        trusted_approval.get("run_id") != run_id or
        trusted_approval.get("id") != approval_id or
        trusted_approval.get("state") != "consumed"):
        raise MCPContractDenied("approval not consumed for this tenant and run")
    if (trusted_execution.get("tenant_id") != tenant_id or
        trusted_execution.get("run_id") != run_id or
        trusted_execution.get("approval_id") != approval_id or
        trusted_execution.get("state") != "reserved"):
        raise MCPContractDenied("MCP execution not reserved for this approval")
    call = canonical_tool_call(
        tool_name=tool_name, arguments=arguments, allowed_tools=allowed_tools,
        approved_tool=trusted_approval.get("tool_name"),
        approved_arguments_sha256=trusted_approval.get("arguments_sha256"),
        idempotency_key=trusted_execution.get("idempotency_key"),
    )
    return {"tenant_id": tenant_id, "run_id": run_id,
            "approval_id": approval_id, **call}
