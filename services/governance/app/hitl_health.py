"""Read-only, tenant-scoped HITL outbox operational health.

Never returns event payloads, secrets or personal data. No scheduler, network
calls, automatic replay or external effects.
"""
from uuid import UUID

class HealthQueryDenied(PermissionError):
    pass

def outbox_health(connection,*,tenant_id,warning_pending=100,warning_dead=1,
                  warning_oldest_seconds=300,warning_expired_leases=1,warning_uncertain_remote=1):
    if any(not isinstance(x,int) or isinstance(x,bool) or x<0
           for x in (warning_pending,warning_dead,warning_oldest_seconds,warning_expired_leases,warning_uncertain_remote)):
        raise ValueError("nonnegative integer alert thresholds required")
    tenant=str(UUID(str(tenant_id)))
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
            cur.execute("""SELECT status,count(*)::bigint
                           FROM hitl.outbox WHERE tenant_id=%s
                           GROUP BY status""",(tenant,))
            counts={"pending":0,"leased":0,"delivered":0,"dead":0}
            for status,n in cur.fetchall():
                if status not in counts:
                    raise HealthQueryDenied("unexpected outbox status")
                counts[status]=int(n)
            cur.execute("""SELECT COALESCE(EXTRACT(EPOCH FROM
                            (now()-MIN(created_at))),0)
                           FROM hitl.outbox WHERE tenant_id=%s
                           AND status='pending'""",(tenant,))
            row=cur.fetchone()
            age=max(0,int(row[0] or 0))
            cur.execute("""SELECT count(*)::bigint FROM hitl.outbox
                           WHERE tenant_id=%s AND status='leased'
                             AND leased_until<now()""",(tenant,))
            expired_leases=int(cur.fetchone()[0])
            cur.execute("""SELECT count(*)::bigint FROM hitl.remote_delivery_receipts
                           WHERE tenant_id=%s AND state='uncertain'""",(tenant,))
            uncertain_remote=int(cur.fetchone()[0])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    alerts=[]
    if counts["pending"]>=warning_pending and counts["pending"]>0:
        alerts.append("pending_backlog")
    if counts["dead"]>=warning_dead and counts["dead"]>0:
        alerts.append("dead_letters")
    if counts["pending"] and age>=warning_oldest_seconds:
        alerts.append("oldest_pending_age")
    if expired_leases>=warning_expired_leases and expired_leases>0:
        alerts.append("expired_leases")
    if uncertain_remote>=warning_uncertain_remote and uncertain_remote>0:
        alerts.append("uncertain_remote_delivery")
    return {"tenant_id":tenant,"expired_leases":expired_leases,
            "uncertain_remote_deliveries":uncertain_remote,"counts":counts,"oldest_pending_seconds":age,
            "alerts":alerts,"healthy":not alerts}
