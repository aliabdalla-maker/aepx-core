"""Postgres outbox lease primitives; transport-agnostic, no network delivery.

Authenticated tenant and worker identity must be provided by trusted caller.
Connection role must enforce tenant RLS; caller must not use owner/BYPASSRLS.
"""
import uuid

def _scope(cur,tenant_id):
    tenant=str(uuid.UUID(str(tenant_id)))
    cur.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
    return tenant

def claim(connection,*,tenant_id,worker_id,limit=10,lease_seconds=60,max_attempts=8):
    if not worker_id or not 1<=limit<=100 or not 1<=lease_seconds<=3600 or max_attempts<1:
        raise ValueError("invalid worker, batch or lease")
    try:
        with connection.cursor() as cur:
            tenant=_scope(cur,tenant_id)
            cur.execute("""WITH candidates AS (
              SELECT id FROM hitl.outbox
              WHERE tenant_id=%s AND attempts < %s AND
                ((status='pending' AND next_attempt_at<=now()) OR
                 (status='leased' AND leased_until<now()))
              ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT %s)
              UPDATE hitl.outbox AS o
              SET status='leased',lease_owner=%s,
                  leased_until=now()+(%s * interval '1 second'),
                  attempts=o.attempts+1
              FROM candidates WHERE o.id=candidates.id
              RETURNING o.id,o.topic,o.payload,o.attempts""",
              (tenant,max_attempts,limit,worker_id,lease_seconds))
            rows=cur.fetchall()
        connection.commit()
        return rows
    except Exception:
        connection.rollback()
        raise

def settle(connection,*,tenant_id,event_id,worker_id,delivered,error=None,
           retry_seconds=30,max_attempts=8,attempt_number=None):
    if not worker_id or not 1<=retry_seconds<=86400 or max_attempts<1 or not isinstance(attempt_number,int) or attempt_number<1:
        raise ValueError("invalid worker or retry policy")
    try:
        with connection.cursor() as cur:
            tenant=_scope(cur,tenant_id)
            cur.execute("""UPDATE hitl.outbox SET
              status=CASE WHEN %s THEN 'delivered'
                          WHEN attempts >= %s THEN 'dead'
                          ELSE 'pending' END,
              delivered_at=CASE WHEN %s THEN now() ELSE delivered_at END,
              next_attempt_at=now()+(%s * interval '1 second'),
              last_error=%s,lease_owner=NULL,leased_until=NULL
              WHERE tenant_id=%s AND id=%s AND status='leased'
                AND lease_owner=%s AND attempts=%s AND leased_until>now()
              RETURNING id""",
              (delivered,max_attempts,delivered,retry_seconds,
               None if delivered else (error or "delivery failed")[:500],
               tenant,str(uuid.UUID(str(event_id))),worker_id,attempt_number))
            row=cur.fetchone()
            if not row:
                raise PermissionError("lease missing, expired or not owned")
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise

def reap_exhausted(connection,*,tenant_id,max_attempts=8,limit=100):
    """Dead-letter exhausted pending or expired leased rows, without delivery.

    Caller supplies a verified tenant and non-BYPASSRLS connection.
    This is required because crashed workers may exhaust their attempts
    without ever reaching settle().
    """
    if not isinstance(max_attempts,int) or max_attempts<1 or not isinstance(limit,int) or not 1<=limit<=1000:
        raise ValueError("invalid exhaustion policy")
    try:
        with connection.cursor() as cur:
            tenant=_scope(cur,tenant_id)
            cur.execute("""WITH exhausted AS (
                SELECT id FROM hitl.outbox
                WHERE tenant_id=%s AND attempts >= %s
                  AND (status='pending' OR
                       (status='leased' AND leased_until<now()))
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT %s
            )
            UPDATE hitl.outbox AS o SET status='dead',
                lease_owner=NULL,leased_until=NULL,
                last_error=COALESCE(o.last_error,'maximum attempts exhausted')
            FROM exhausted WHERE o.id=exhausted.id
            RETURNING o.id""",(tenant,max_attempts,limit))
            rows=cur.fetchall()
        connection.commit()
        return [row[0] for row in rows]
    except Exception:
        connection.rollback()
        raise

def lease_is_current(connection, *, tenant_id, event_id, worker_id, attempt_number):
    """Read-only preflight; settlement still enforces the authoritative fence.

    A successful preflight does NOT reserve the lease for external execution.
    """
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker identity required")
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
        raise ValueError("valid attempt number required")
    try:
        with connection.cursor() as cur:
            tenant = _scope(cur, tenant_id)
            cur.execute("""SELECT EXISTS(
                SELECT 1 FROM hitl.outbox WHERE tenant_id=%s AND id=%s
                AND status='leased' AND lease_owner=%s
                AND attempts=%s AND leased_until>now()
            )""", (tenant, str(uuid.UUID(str(event_id))), worker_id, attempt_number))
            row = cur.fetchone()
        connection.commit()
        return bool(row and row[0] is True)
    except Exception:
        connection.rollback()
        raise
