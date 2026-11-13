"""Safe receipt reservation and reconciliation for uncertain remote delivery.

No network calls. Reservation must be committed before invoking a provider.
A crashed or timed-out invocation stays 'uncertain' and cannot be blindly
retried. Only trusted reconciliation can transition to confirmed/failed_safe.
"""
from uuid import UUID

class ReconciliationRequired(PermissionError):
    pass

def _identifiers(tenant_id,event_id,provider,idempotency_key):
    tenant=str(UUID(str(tenant_id)))
    event=str(UUID(str(event_id)))
    if (not isinstance(provider,str) or not 1<=len(provider.strip())<=128
        or not isinstance(idempotency_key,str)
        or not 8<=len(idempotency_key.strip())<=200):
        raise ValueError("valid provider and idempotency key required")
    return tenant,event,provider.strip(),idempotency_key.strip()

def reserve_remote(connection,*,tenant_id,event_id,provider,idempotency_key):
    tenant,event,provider,key=_identifiers(tenant_id,event_id,provider,idempotency_key)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
            cur.execute("""SELECT topic FROM hitl.outbox WHERE tenant_id=%s AND id=%s
                           FOR UPDATE""",(tenant,event))
            row=cur.fetchone()
            if not row or row[0]!="hitl.approval.consumed":
                raise ReconciliationRequired("eligible outbox event not found")
            cur.execute("""INSERT INTO hitl.remote_delivery_receipts
                           (tenant_id,event_id,provider,idempotency_key,state)
                           VALUES(%s,%s,%s,%s,'uncertain')
                           ON CONFLICT (tenant_id,event_id) DO NOTHING
                           RETURNING event_id""",(tenant,event,provider,key))
            reserved=cur.fetchone()
            if not reserved:
                raise ReconciliationRequired("event already reserved: reconcile before retry")
        connection.commit()
        return {"state":"uncertain","idempotency_key":key}
    except Exception:
        connection.rollback()
        raise

def reconcile_remote(connection,*,tenant_id,event_id,provider,idempotency_key,
                     verified_state,evidence_reference,reviewer_id,authorized=False):
    if not authorized:
        raise ReconciliationRequired("verified operator authorization required")
    if verified_state not in ("confirmed","failed_safe"):
        raise ValueError("only independently verified terminal outcomes allowed")
    if (not isinstance(evidence_reference,str) or len(evidence_reference.strip())<8
        or not isinstance(reviewer_id,str) or len(reviewer_id.strip())<8):
        raise ValueError("reconciliation evidence and reviewer required")
    tenant,event,provider,key=_identifiers(tenant_id,event_id,provider,idempotency_key)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
            cur.execute("""UPDATE hitl.remote_delivery_receipts
                           SET state=%s,updated_at=now()
                           WHERE tenant_id=%s AND event_id=%s
                             AND provider=%s AND idempotency_key=%s
                             AND state='uncertain'
                           RETURNING event_id""",
                        (verified_state,tenant,event,provider,key))
            if cur.fetchone() is None:
                raise ReconciliationRequired("receipt not uncertain or does not match")
            cur.execute("""INSERT INTO hitl.events
                           (tenant_id,approval_id,event,actor_id)
                           SELECT tenant_id,(payload->>'approval_id')::uuid,
                                  %s,%s FROM hitl.outbox
                           WHERE tenant_id=%s AND id=%s""",
                        ("remote_"+verified_state+":"+evidence_reference.strip()[:200],
                         reviewer_id.strip(),tenant,event))
            if cur.rowcount!=1:
                raise ReconciliationRequired("reconciliation audit event missing")
        connection.commit()
        return {"state":verified_state,"event_id":event}
    except Exception:
        connection.rollback()
        raise
