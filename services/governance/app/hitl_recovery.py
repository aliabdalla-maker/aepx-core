"""Fail-closed, operator-authorised dead-letter replay.

No external action is executed here. An audited operator may move one
dead-letter event back to pending after investigating downstream idempotency.
Caller MUST authenticate operator and supply restricted non-BYPASSRLS DB role.
"""
from uuid import UUID

class RecoveryDenied(PermissionError):
    pass

def requeue_dead_letter(connection,*,tenant_id,event_id,operator_id,ticket_id,
                        reason,approved=False,idempotency_verified=False):
    if not approved or not idempotency_verified:
        raise RecoveryDenied("explicit operator approval and deduplication review required")
    if not all(isinstance(x,str) and 8<=len(x.strip())<=500 for x in
               (operator_id,ticket_id,reason)):
        raise ValueError("operator, ticket and reason must be 8-500 characters")
    tenant=str(UUID(str(tenant_id)))
    event=str(UUID(str(event_id)))
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
            cur.execute("""UPDATE hitl.outbox SET status='pending',attempts=0,
                          next_attempt_at=now(),lease_owner=NULL,leased_until=NULL,
                          last_error='operator-authorised retry'
                          WHERE tenant_id=%s AND id=%s AND status='dead'
                          RETURNING id""",(tenant,event))
            if cur.fetchone() is None:
                raise RecoveryDenied("event not found or not dead")
            cur.execute("""INSERT INTO hitl.outbox_recovery_audit
                         (tenant_id,event_id,operator_id,ticket_id,reason)
                         VALUES(%s,%s,%s,%s,%s)""",
                        (tenant,event,operator_id.strip(),ticket_id.strip(),reason.strip()))
        connection.commit()
        return {"status":"pending","event_id":event}
    except Exception:
        connection.rollback()
        raise
