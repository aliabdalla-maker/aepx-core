"""Explicitly controlled HITL outbox dispatcher.

Default mode is DRY RUN: no DB claims and no network calls.
The caller must supply a trusted tenant and worker identity, a restricted
non-BYPASSRLS database connection and an approved idempotent delivery adapter.
"""
import os
from uuid import UUID
from app.hitl_outbox import claim,settle

class DispatchDisabled(PermissionError):
    pass

def dispatch_batch(connection,*,tenant_id,worker_id,deliver=None,enabled=False,
                   limit=10,lease_seconds=60,max_attempts=8,retry_seconds=30):
    if not enabled or os.getenv("HITL_DISPATCH_ENABLED")!="yes":
        return {"mode":"dry-run","claimed":0,"delivered":0,"failed":0}
    if deliver is None or not callable(deliver):
        raise DispatchDisabled("an explicitly configured delivery adapter is required")
    tenant=str(UUID(str(tenant_id)))
    if not worker_id or not isinstance(worker_id,str):
        raise ValueError("verified worker identity required")
    rows=claim(connection,tenant_id=tenant,worker_id=worker_id,limit=limit,
               lease_seconds=lease_seconds,max_attempts=max_attempts)
    delivered=failed=0
    for event_id,topic,payload,attempt in rows:
        ok=False
        error=None
        try:
            if topic!="hitl.approval.consumed":
                raise ValueError("unapproved outbox topic")
            # Adapter MUST deduplicate by stable event_id and avoid unbounded
            # side effects. Delivery and settlement cannot be atomic across
            # independent systems.
            deliver(event_id=str(event_id),topic=topic,payload=payload,tenant_id=tenant)
            ok=True
        except Exception:
            error="delivery adapter failed"  # never persist secrets/tracebacks
        try:
            settle(connection,tenant_id=tenant,event_id=event_id,
                   worker_id=worker_id,attempt_number=attempt,
                   delivered=ok,error=error,retry_seconds=retry_seconds,
                   max_attempts=max_attempts)
        except Exception:
            # A failed settlement may cause redelivery after the lease expires.
            # Fail closed and require downstream idempotency on event_id.
            raise
        delivered+=int(ok)
        failed+=int(not ok)
    return {"mode":"enabled","claimed":len(rows),"delivered":delivered,"failed":failed}
