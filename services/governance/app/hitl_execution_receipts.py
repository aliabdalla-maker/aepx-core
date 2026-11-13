"""Atomic idempotency for *local PostgreSQL* business actions only.

The trusted callback MUST use the provided cursor and MUST NOT perform any
network call or independently commit. Not suitable for remote MCP delivery.
"""
from uuid import UUID

class ExecutionDenied(PermissionError):
    pass

def execute_local_once(connection,*,tenant_id,event_id,action_hash,tool_name,
                       apply_local,approved=False):
    if not approved:
        raise ExecutionDenied("independent approval verification required")
    if not callable(apply_local):
        raise TypeError("local transaction callback required")
    if not isinstance(action_hash,str) or len(action_hash)!=64 or any(
        c not in "0123456789abcdef" for c in action_hash
    ):
        raise ValueError("valid SHA-256 action hash required")
    if not isinstance(tool_name,str) or not 1<=len(tool_name.strip())<=128:
        raise ValueError("tool name required")
    tenant=str(UUID(str(tenant_id)))
    event=str(UUID(str(event_id)))
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
            # Serializes duplicate attempts, including across workers.
            cur.execute("""SELECT topic,payload FROM hitl.outbox
                           WHERE tenant_id=%s AND id=%s FOR UPDATE""",(tenant,event))
            row=cur.fetchone()
            if not row or row[0]!="hitl.approval.consumed":
                raise ExecutionDenied("approved event not found")
            payload=row[1]
            if not isinstance(payload,dict) or payload.get("action_hash")!=action_hash:
                raise ExecutionDenied("event action mismatch")
            cur.execute("""SELECT action_hash,tool_name FROM hitl.execution_receipts
                           WHERE tenant_id=%s AND event_id=%s""",(tenant,event))
            existing=cur.fetchone()
            if existing:
                if existing[0]!=action_hash or existing[1]!=tool_name:
                    raise ExecutionDenied("event receipt mismatch")
                result="duplicate"
            else:
                # Callback must be a trusted, strictly local SQL operation.
                # Any exception rolls back both effect and receipt.
                apply_local(cur)
                cur.execute("""INSERT INTO hitl.execution_receipts
                               (tenant_id,event_id,action_hash,tool_name)
                               VALUES(%s,%s,%s,%s)""",
                            (tenant,event,action_hash,tool_name))
                result="applied"
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
