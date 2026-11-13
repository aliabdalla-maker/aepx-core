"""Transactional, single-winner claim for a committed remote MCP intent.

The caller MUST bind a verified tenant on a non-BYPASSRLS role, use a fresh
transaction after reservation commit, and commit the claim BEFORE network I/O.
No provider call is made here. Ambiguous dispatch must be reconciled, not retried.
"""
from dataclasses import dataclass
from uuid import UUID
import re

_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z')

class DispatchClaimDenied(PermissionError):
    pass

@dataclass(frozen=True)
class DispatchClaim:
    tenant_id: str
    request_id: str
    idempotency_key: str

def claim_dispatch(cursor, *, tenant_id, request_id, idempotency_key):
    for value in (tenant_id, request_id):
        try:
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise DispatchClaimDenied("canonical tenant and request IDs required") from exc
    if type(idempotency_key) is not str or _KEY.fullmatch(idempotency_key) is None:
        raise DispatchClaimDenied("invalid idempotency key")
    cursor.execute(
        """UPDATE mcp_remote_execution_intents
           SET state = 'dispatched', updated_at = now()
           WHERE tenant_id = %s AND request_id = %s
             AND idempotency_key = %s AND state = 'reserved'
           RETURNING request_id""",
        (tenant_id, request_id, idempotency_key),
    )
    row = cursor.fetchone()
    if row is None or str(row[0]) != request_id:
        raise DispatchClaimDenied("intent absent, invisible, or already claimed")
    return DispatchClaim(tenant_id, request_id, idempotency_key)
