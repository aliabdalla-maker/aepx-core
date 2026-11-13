"""Transactional remote MCP intent reservation (no network dispatch).

The caller must establish a trusted PostgreSQL connection using a non-bypass-RLS
role and SET LOCAL app.tenant_id inside the transaction. No commit here:
the caller owns transaction lifecycle and must commit before remote I/O.
"""
from dataclasses import dataclass
from uuid import UUID

class ReservationDenied(PermissionError):
    pass

@dataclass(frozen=True)
class IntentReservation:
    tenant_id: str
    request_id: str
    approval_id: str
    action_hash: str
    resource_id: str
    tool_name: str
    protocol_version: str
    idempotency_key: str

_COLUMNS = ("tenant_id", "request_id", "approval_id", "action_hash",
            "resource_id", "tool_name", "protocol_version", "idempotency_key")

def reserve_intent(cursor, intent):
    """Insert once, or return the existing exact intent; fail closed on conflict.

    Must run within a transaction. The UNIQUE constraints serialize concurrent
    insertions. Caller must not dispatch until the transaction commits.
    """
    if not isinstance(intent, IntentReservation):
        raise ReservationDenied("typed reservation required")
    for key in ("tenant_id", "request_id", "approval_id"):
        value = getattr(intent, key)
        try:
            if str(UUID(value)) != value:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ReservationDenied("invalid UUID: " + key) from exc
    if any(not isinstance(getattr(intent, key), str) or not getattr(intent, key)
           for key in _COLUMNS):
        raise ReservationDenied("missing reservation field")
    values = tuple(getattr(intent, key) for key in _COLUMNS)
    cursor.execute(
        """INSERT INTO mcp_remote_execution_intents
        (tenant_id, request_id, approval_id, action_hash, resource_id,
         tool_name, protocol_version, idempotency_key)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING RETURNING tenant_id, request_id,
        approval_id, action_hash, resource_id, tool_name, protocol_version,
        idempotency_key, state""", values)
    row = cursor.fetchone()
    if row is not None:
        return "created"
    cursor.execute(
        """SELECT tenant_id, request_id, approval_id, action_hash, resource_id,
        tool_name, protocol_version, idempotency_key, state
        FROM mcp_remote_execution_intents
        WHERE tenant_id = %s AND (request_id = %s OR idempotency_key = %s
          OR (approval_id = %s AND action_hash = %s))
        FOR UPDATE""",
        (intent.tenant_id, intent.request_id, intent.idempotency_key,
         intent.approval_id, intent.action_hash))
    rows = cursor.fetchall()
    if len(rows) != 1 or tuple(str(v) for v in rows[0][:8]) != values:
        raise ReservationDenied("conflicting or invisible reservation")
    return "existing"
