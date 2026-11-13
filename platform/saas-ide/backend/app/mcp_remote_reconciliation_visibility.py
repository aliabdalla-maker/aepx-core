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
    return tuple(UncertainIntent(str(row[0]), row[1], row[2]) for row in rows)
