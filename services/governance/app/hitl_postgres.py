"""PostgreSQL HITL transactional core. Caller must supply VERIFIED tenant/actor identity.

No public API and no direct tool execution. Requires migration 20261113_hitl_staging.sql.
DB connection must be a non-owner, non-BYPASSRLS role with restricted grants.
"""
import hashlib
import json
import uuid

class ApprovalError(PermissionError):
    pass

def fingerprint(action):
    if not isinstance(action,dict) or not action:
        raise ValueError("nonempty action object required")
    return hashlib.sha256(json.dumps(action,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def _tenant(db,tenant_id):
    # SET LOCAL is scoped to the same transaction and prevents pool cross-tenant leakage.
    db.execute("SELECT set_config('app.tenant_id', %s, true)",(str(uuid.UUID(str(tenant_id))),))

def consume_with_outbox(connection, *, tenant_id, approval_id, action, idempotency_key, actor_id):
    """Consume approved HITL and enqueue event in ONE DB transaction.

    The caller owns the connection; this function commits on success and rolls
    back on any failure. No external side effect occurs here. Event delivery
    must be idempotent and separately reconciled.
    """
    if not idempotency_key or not actor_id:
        raise ValueError("idempotency_key and authenticated actor required")
    approval_uuid=str(uuid.UUID(str(approval_id)))
    tenant_uuid=str(uuid.UUID(str(tenant_id)))
    event_uuid=str(uuid.uuid4())
    payload={"approval_id":approval_uuid,"action_hash":fingerprint(action),"actor_id":actor_id}
    try:
        with connection.cursor() as cur:
            _tenant(cur,tenant_uuid)
            cur.execute("""SELECT action_hash,status,expires_at > now(),approver_id
                FROM hitl.approvals WHERE id=%s AND tenant_id=%s FOR UPDATE""",
                (approval_uuid,tenant_uuid))
            row=cur.fetchone()
            if not row or row[0]!=payload["action_hash"] or row[1]!="approved" or row[2] is not True or not row[3]:
                raise ApprovalError("approval missing, expired, mismatched or already consumed")
            cur.execute("""UPDATE hitl.approvals SET status='consumed',consumed_at=now()
                WHERE id=%s AND tenant_id=%s AND status='approved'""",(approval_uuid,tenant_uuid))
            if cur.rowcount!=1:
                raise ApprovalError("approval consumption conflict")
            cur.execute("""INSERT INTO hitl.events(tenant_id,approval_id,event,actor_id)
                VALUES(%s,%s,'consumed',%s)""",(tenant_uuid,approval_uuid,actor_id))
            cur.execute("""INSERT INTO hitl.outbox
                (id,tenant_id,idempotency_key,topic,payload,status)
                VALUES(%s,%s,%s,'hitl.approval.consumed',%s::jsonb,'pending')""",
                (event_uuid,tenant_uuid,idempotency_key,json.dumps(payload,sort_keys=True)))
        connection.commit()
        return event_uuid
    except Exception:
        connection.rollback()
        raise
