"""Post-commit reservation verification gate for remote MCP dispatch.

No network call is performed. The caller must supply a fresh transaction
connection and verified tenant identity; the connection MUST not be the
uncommitted reservation transaction.
"""
from dataclasses import dataclass
from uuid import UUID
import re

_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z')

class DispatchNotCommitted(PermissionError):
    pass

@dataclass(frozen=True)
class CommittedIntent:
    tenant_id: str
    request_id: str
    idempotency_key: str

def verify_committed_intent(cursor, *, tenant_id, request_id, idempotency_key):
    """Read a reserved intent from an independent, committed-read transaction.

    This does not prove that the caller used a different connection. The
    orchestrator must enforce separate connections and trusted tenant context.
    """
    try:
        if (type(tenant_id) is not str or type(request_id) is not str
                or str(UUID(tenant_id)) != tenant_id or str(UUID(request_id)) != request_id):
            raise ValueError("noncanonical")
    except (TypeError, AttributeError, ValueError) as exc:
        raise DispatchNotCommitted("invalid intent identifiers") from exc
    if type(idempotency_key) is not str or _KEY.fullmatch(idempotency_key) is None:
        raise DispatchNotCommitted("missing idempotency key")
    cursor.execute(
        """SELECT state FROM mcp_remote_execution_intents
        WHERE tenant_id = %s AND request_id = %s AND idempotency_key = %s""",
        (tenant_id, request_id, idempotency_key))
    row = cursor.fetchone()
    if row is None or row[0] != "reserved":
        raise DispatchNotCommitted("intent is absent, uncommitted or not reserved")
    return CommittedIntent(tenant_id, request_id, idempotency_key)
