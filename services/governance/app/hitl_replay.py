"""Read-only verification of an already-committed HITL outbox event.

A replay is successful only if the tenant, idempotency key, approval ID,
action fingerprint and actor all match. The database role must be subject
to tenant RLS. Never infer replay success from an idempotency key alone.
"""
import json
from uuid import UUID
from app.hitl_postgres import fingerprint

def find_matching_replay(connection, *, tenant_id, approval_id, action, idempotency_key, actor_id):
    tenant=str(UUID(str(tenant_id)))
    approval=str(UUID(str(approval_id)))
    expected_hash=fingerprint(action)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)",(tenant,))
            cur.execute("""SELECT id,payload FROM hitl.outbox
                WHERE tenant_id=%s AND idempotency_key=%s
                  AND topic='hitl.approval.consumed'
                LIMIT 1""",(tenant,idempotency_key))
            row=cur.fetchone()
            if row is None:
                return None
            payload=row[1]
            if isinstance(payload,str):
                payload=json.loads(payload)
            if not isinstance(payload,dict):
                return None
            if payload.get("approval_id")!=approval or payload.get("action_hash")!=expected_hash or payload.get("actor_id")!=actor_id:
                return None
            return str(row[0])
    finally:
        connection.rollback()  # clears transaction-local tenant setting
