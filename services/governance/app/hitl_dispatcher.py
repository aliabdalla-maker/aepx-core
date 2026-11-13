"""Explicitly controlled, tenant-scoped HITL outbox dispatcher.

Default is dry-run. External adapters must implement event-id idempotency;
remote delivery and PostgreSQL settlement are NOT atomic.
"""
import os
import hashlib
import time
from uuid import UUID
from app.hitl_outbox import claim, settle, reap_exhausted, lease_is_current

class DispatchDisabled(PermissionError):
    pass

def dispatch_batch(connection, *, tenant_id, worker_id, deliver=None,
                   enabled=False, limit=10, lease_seconds=60,
                   max_attempts=8, retry_seconds=30, max_batch_seconds=30):
    if not enabled or os.getenv("HITL_DISPATCH_ENABLED") != "yes":
        return {"mode": "dry-run", "claimed": 0, "delivered": 0, "failed": 0}
    if not callable(deliver):
        raise DispatchDisabled("explicit idempotent delivery adapter required")
    if (not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100 or
        not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600 or
        not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1 or
        not isinstance(retry_seconds, int) or isinstance(retry_seconds, bool) or not 1 <= retry_seconds <= 86400):
        raise ValueError("invalid dispatcher bounds")
    if (not isinstance(max_batch_seconds, (int, float)) or isinstance(max_batch_seconds, bool)
        or not 0 < max_batch_seconds < lease_seconds):
        raise ValueError("batch deadline must be shorter than lease")
    tenant = str(UUID(str(tenant_id)))
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("verified worker identity required")
    # Begin the deadline before database work, so slow claim/recovery time
    # cannot silently extend the permitted batch processing window.
    deadline = time.monotonic() + max_batch_seconds
    # Recover crashed workers that exhausted attempts; do not redeliver them.
    reaped = reap_exhausted(connection, tenant_id=tenant, max_attempts=max_attempts)
    rows = claim(connection, tenant_id=tenant, worker_id=worker_id,
                 limit=limit, lease_seconds=lease_seconds,
                 max_attempts=max_attempts)
    delivered = failed = stale = 0
    for event_id, topic, payload, attempt in rows:
        # Never begin another callback once the bounded batch window expires.
        # Unprocessed leased rows recover through lease expiry.
        if time.monotonic() >= deadline:
            break
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("invalid lease fencing attempt")
        ok = False
        if topic == "hitl.approval.consumed" and isinstance(payload, dict):
            # Database errors propagate: never settle after an uncertain preflight.
            current = lease_is_current(connection, tenant_id=tenant, event_id=event_id,
                                       worker_id=worker_id, attempt_number=attempt)
            if not current:
                stale += 1
                continue
            # A slow database preflight must not authorize a callback after
            # the batch deadline. Leave this lease for normal expiry/recovery.
            if time.monotonic() >= deadline:
                break
        try:
            if topic != "hitl.approval.consumed" or not isinstance(payload, dict):
                raise PermissionError("unsupported event")
            deliver(event_id=str(event_id), topic=topic, payload=payload,
                    tenant_id=tenant)
            ok = True
        except PermissionError:
            # Unsupported topics may be retried/dead-lettered by policy.
            pass
        except Exception:
            # Delivery adapter failure: never expose exception details.
            pass
        try:
            # Deterministic per-event jitter prevents synchronized retry storms.
            jitter = int.from_bytes(hashlib.sha256(str(event_id).encode()).digest()[:2], "big") % 11
            delay = min(86400, retry_seconds * (2 ** min(attempt - 1, 11)) + jitter)
            settle(connection, tenant_id=tenant, event_id=event_id,
                   worker_id=worker_id, attempt_number=attempt,
                   delivered=ok, error=None if ok else "delivery adapter failed",
                   retry_seconds=delay,
                   max_attempts=max_attempts)
        except PermissionError:
            # Stale lease must never be settled by an older worker.
            stale += 1
            continue
        delivered += int(ok)
        failed += int(not ok)
    return {"mode": "enabled", "claimed": len(rows), "deferred": len(rows) - delivered - failed - stale, "delivered": delivered,
            "failed": failed, "stale": stale, "reaped": len(reaped)}
