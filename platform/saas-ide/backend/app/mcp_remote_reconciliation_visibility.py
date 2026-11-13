"""Read-only, tenant-scoped visibility into uncertain MCP intents.

No network calls, retries, terminal-state changes or cross-tenant scans.
Call with a verified tenant bound to a non-BYPASSRLS PostgreSQL transaction.
"""
from dataclasses import dataclass
from uuid import UUID

class ReconciliationVisibilityDenied(PermissionError):
    pass

@dataclass(frozen=True)
class UncertainIntent:
    request_id: str
    idempotency_key: str
    updated_at: object

def list_uncertain_intents(cursor, *, tenant_id, limit=50):
    try:
        if type(tenant_id) is not str or str(UUID(tenant_id)) != tenant_id:
            raise ValueError("noncanonical")
    except (TypeError, AttributeError, ValueError) as exc:
        raise ReconciliationVisibilityDenied("canonical tenant UUID required") from exc
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ReconciliationVisibilityDenied("invalid bounded result limit")
    cursor.execute(
        """SELECT request_id, idempotency_key, updated_at
           FROM mcp_remote_execution_intents
           WHERE tenant_id = %s AND state = 'uncertain'
           ORDER BY updated_at ASC, request_id ASC LIMIT %s""",
        (tenant_id, limit))
    rows = cursor.fetchall()
    if type(rows) not in (list, tuple) or len(rows) > limit:
        raise ReconciliationVisibilityDenied("invalid or unbounded result set")
    result = []
    for row in rows:
        if type(row) not in (tuple, list) or len(row) != 3:
            raise ReconciliationVisibilityDenied("malformed result row")
        request_id, idempotency_key, updated_at = row
        try:
            if str(UUID(str(request_id))) != str(request_id):
                raise ValueError("noncanonical request ID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ReconciliationVisibilityDenied("invalid request ID") from exc
        if type(idempotency_key) is not str or not 8 <= len(idempotency_key) <= 128:
            raise ReconciliationVisibilityDenied("invalid idempotency key")
        result.append(UncertainIntent(str(request_id), idempotency_key, updated_at))
    return tuple(result)
