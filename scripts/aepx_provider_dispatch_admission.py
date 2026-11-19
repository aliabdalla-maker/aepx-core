"""Pure, offline provider dispatch admission policy. No provider calls.

A positive result is only a local policy precondition, not proof of
transactional ownership, authenticated approval or billing safety.
"""
import re

KEY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

class DispatchDenied(ValueError):
    pass

def authorize_first_dispatch(*, reservation_status, approval_verified,
                             lease_fence, idempotency_key, tenant_id,
                             request_id, budget_committed, worker_isolated):
    """Fail closed unless every required first-dispatch signal is present.

    Values must originate from trusted server-side verification. This helper
    does not authenticate those inputs or claim an exclusive durable lease.
    """
    if reservation_status != "reserved":
        raise DispatchDenied("new reservation required; replays never dispatch")
    if approval_verified is not True or budget_committed is not True or worker_isolated is not True:
        raise DispatchDenied("approval, committed budget and isolation required")
    if type(lease_fence) is not int or lease_fence <= 0:
        raise DispatchDenied("positive integer fencing token required")
    if not isinstance(idempotency_key, str) or not KEY.fullmatch(idempotency_key):
        raise DispatchDenied("invalid provider idempotency key")
    if not isinstance(tenant_id, str) or not tenant_id or len(tenant_id) > 128:
        raise DispatchDenied("missing tenant identity")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        raise DispatchDenied("invalid request identity")
    return {"decision": "eligible_for_fenced_dispatch",
            "tenant_id": tenant_id, "request_id": request_id,
            "lease_fence": lease_fence, "idempotency_key": idempotency_key}
