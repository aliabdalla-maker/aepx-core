"""Atomic, fail-closed MCP dispatch claim with exact approved tool contract.

Caller supplies authenticated tenant and trusted server/tool policy. No HTTP
request or provider side effect occurs here. Once claimed, outcome is uncertain
until an independently verified provider result is persisted.
"""
from sqlalchemy import text
from .phase23 import _scope
from .mcp_contract_gate import canonical_tool_call, MCPContractDenied


def claim_approved_mcp_call(db, *, tenant_id, run_id, approval_id,
                            server_id, tool_name, arguments, allowed_tools):
    """Validate under run/approval/execution locks and claim in one transaction."""
    try:
        _scope(db, tenant_id)
        run = db.execute(text("""
            SELECT id FROM ide_agent_runs
            WHERE tenant_id=:tenant AND id=:run
              AND status IN ('approved','running') FOR UPDATE
        """), {"tenant":tenant_id,"run":run_id}).first()
        if run is None:
            raise MCPContractDenied("inactive or cancelled run")
        row = db.execute(text("""
            SELECT a.server_name,a.tool_name,a.args_sha256,
                   e.idempotency_key
            FROM ide_tool_approvals a
            JOIN ide_memberships requester ON requester.tenant_id=a.tenant_id
              AND requester.subject=a.requested_by
              AND requester.role IN ('owner','admin','editor')
            JOIN ide_memberships approver ON approver.tenant_id=a.tenant_id
              AND approver.subject=a.decided_by
              AND approver.role IN ('owner','admin')
            JOIN ide_mcp_executions e ON e.tenant_id=a.tenant_id
              AND e.run_id=a.run_id AND e.approval_id=a.id
            WHERE a.tenant_id=:tenant AND a.run_id=:run AND a.id=:approval
              AND a.state='consumed' AND e.state='reserved'
            FOR UPDATE OF a,e
        """), {"tenant":tenant_id,"run":run_id,"approval":approval_id}).mappings().first()
        if row is None or row["server_name"] != server_id:
            raise MCPContractDenied("no reserved execution with valid approval")
        bound = canonical_tool_call(
            tool_name=tool_name,arguments=arguments,allowed_tools=allowed_tools,
            approved_tool=row["tool_name"],
            approved_arguments_sha256=row["args_sha256"],
            idempotency_key=row["idempotency_key"])
        claimed = db.execute(text("""
            UPDATE ide_mcp_executions SET state='dispatching',
                dispatch_started_at=now()
            WHERE tenant_id=:tenant AND run_id=:run AND approval_id=:approval
              AND state='reserved'
            RETURNING idempotency_key
        """), {"tenant":tenant_id,"run":run_id,"approval":approval_id}).first()
        if claimed is None or claimed[0] != bound["idempotency_key"]:
            raise MCPContractDenied("MCP dispatch claim lost or changed")
        db.commit()
        return {"tenant_id":tenant_id,"run_id":run_id,
                "approval_id":approval_id,"server_id":server_id,**bound}
    except Exception:
        db.rollback()
        raise
