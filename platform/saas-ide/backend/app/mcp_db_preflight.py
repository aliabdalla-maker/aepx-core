"""Read tenant-scoped MCP approval evidence before offline preflight.

No network, dispatch transition or side effects. Caller must authenticate tenant.
"""
from sqlalchemy import text
from .phase23 import _scope
from .mcp_contract_gate import MCPContractDenied
from .mcp_preflight import prepare_mcp_preflight


def prepare_mcp_db_preflight(db, *, tenant_id, run_id, approval_id, server_id,
                             tool_name, arguments, discovered_tools,
                             trusted_server_allowlist, trusted_tool_allowlist,
                             request_id, client_name, client_version):
    """Read trusted DB rows and run pure preflight, without claiming execution.

    Roll back the read-only transaction to clear SET LOCAL tenant context.
    A later dispatch MUST revalidate and claim atomically under run lock.
    """
    try:
        _scope(db, tenant_id)
        row = db.execute(text("""
            SELECT a.id,a.tenant_id,a.run_id,a.server_name,a.tool_name,
                   a.args_sha256,a.state,
                   e.approval_id,e.state AS execution_state,e.idempotency_key
            FROM ide_tool_approvals a
            JOIN ide_mcp_executions e
              ON e.tenant_id=a.tenant_id AND e.run_id=a.run_id
             AND e.approval_id=a.id
            JOIN ide_agent_runs r
              ON r.tenant_id=a.tenant_id AND r.id=a.run_id
            WHERE a.tenant_id=:tenant AND a.run_id=:run
              AND a.id=:approval AND r.status IN ('approved','running')
        """), {"tenant":tenant_id,"run":run_id,"approval":approval_id}).mappings().first()
        if row is None or row["server_name"] != server_id:
            raise MCPContractDenied("no matching active tenant-scoped MCP approval")
        approval = {key:row[key] for key in
                    ("id","tenant_id","run_id","tool_name","args_sha256","state")}
        execution = {"tenant_id":row["tenant_id"],"run_id":row["run_id"],
                     "approval_id":row["approval_id"],
                     "state":row["execution_state"],
                     "idempotency_key":row["idempotency_key"]}
        return prepare_mcp_preflight(
            tenant_id=tenant_id,run_id=run_id,approval_id=approval_id,
            server_id=server_id,tool_name=tool_name,arguments=arguments,
            discovered_tools=discovered_tools,
            trusted_server_allowlist=trusted_server_allowlist,
            trusted_tool_allowlist=trusted_tool_allowlist,
            trusted_approval=approval,trusted_execution=execution,
            request_id=request_id,client_name=client_name,
            client_version=client_version)
    finally:
        db.rollback()
