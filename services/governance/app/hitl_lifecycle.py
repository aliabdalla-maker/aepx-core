"""Tenant-scoped HITL request and decision transactions. No external execution."""
from uuid import uuid4,UUID
from datetime import datetime,timezone
from app.hitl_postgres import fingerprint

class DecisionConflict(Exception):
    pass

def create_request(connection,*,tenant_id,action,requester_id,expires_at):
    if expires_at<=datetime.now(timezone.utc):
        raise ValueError("approval expiry must be in the future")
    tenant=str(UUID(str(tenant_id)))
    approval=str(uuid4())
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)",(tenant,))
            cur.execute("""INSERT INTO hitl.approvals
                (id,tenant_id,action_hash,requester_id,status,expires_at)
                VALUES (%s,%s,%s,%s,'pending',%s)""",
                (approval,tenant,fingerprint(action),requester_id,expires_at))
            cur.execute("""INSERT INTO hitl.events
                (tenant_id,approval_id,event,actor_id)
                VALUES (%s,%s,'requested',%s)""",(tenant,approval,requester_id))
        connection.commit()
        return approval
    except Exception:
        connection.rollback()
        raise

def decide_request(connection,*,tenant_id,approval_id,approver_id,decision):
    if decision not in ("approved","rejected"):
        raise ValueError("invalid decision")
    tenant=str(UUID(str(tenant_id)))
    approval=str(UUID(str(approval_id)))
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)",(tenant,))
            cur.execute("""UPDATE hitl.approvals
                SET status=%s,approver_id=%s
                WHERE id=%s AND tenant_id=%s AND status='pending'
                  AND expires_at>now() AND requester_id<>%s
                RETURNING id""",(decision,approver_id,approval,tenant,approver_id))
            if cur.fetchone() is None:
                raise DecisionConflict("approval missing, expired, already decided or self-approved")
            cur.execute("""INSERT INTO hitl.events
                (tenant_id,approval_id,event,actor_id)
                VALUES (%s,%s,%s,%s)""",(tenant,approval,decision,approver_id))
        connection.commit()
        return decision
    except Exception:
        connection.rollback()
        raise
