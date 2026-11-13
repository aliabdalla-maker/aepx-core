"""Fail-closed offline reconciliation for ambiguous remote MCP dispatches.

Never issues provider calls, never retries, and never marks success/failure.
The caller supplies a trusted, tenant-bound PostgreSQL transaction.
"""
from uuid import UUID

class ReconciliationDenied(PermissionError):
    pass

def mark_stale_dispatch_uncertain(cursor, *, tenant_id, request_id, minimum_age_seconds):
    """Atomically move a stale dispatched intent to uncertain.

    The timeout only authorizes quarantine. Provider evidence is required for
    terminal resolution; it must be authenticated and validated elsewhere.
    """
    for value in (tenant_id, request_id):
        try:
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("noncanonical UUID")
        except (TypeError, AttributeError, ValueError) as exc:
            raise ReconciliationDenied("canonical tenant/request UUID required") from exc
    if type(minimum_age_seconds) is not int or not 1 <= minimum_age_seconds <= 86400:
        raise ReconciliationDenied("invalid reconciliation age")
    cursor.execute(
        """UPDATE mcp_remote_execution_intents
           SET state = 'uncertain', updated_at = now()
           WHERE tenant_id = %s AND request_id = %s AND state = 'dispatched'
             AND updated_at <= now() - (%s * interval '1 second')
           RETURNING request_id""",
        (tenant_id, request_id, minimum_age_seconds))
    row = cursor.fetchone()
    if row is None or str(row[0]) != request_id:
        raise ReconciliationDenied("intent not stale, not dispatched, or invisible")
    return "uncertain"
