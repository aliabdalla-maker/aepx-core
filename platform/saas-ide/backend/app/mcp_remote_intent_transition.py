"""Offline transactional state update for a reserved MCP intent.

Caller owns transaction, tenant RLS context, authenticated evidence validation,
and commit. No network execution, implicit retries, or schema migrations.
"""
from uuid import UUID
from .mcp_remote_intent_state import IntentState, validate_transition

class TransitionDenied(PermissionError):
    pass

def transition_intent(cursor, *, tenant_id, request_id, current, target,
                      provider_evidence=False):
    for value in (tenant_id, request_id):
        try:
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise TransitionDenied("canonical tenant and request UUID required") from exc
    validate_transition(current, target, provider_evidence=provider_evidence)
    cursor.execute(
        """UPDATE mcp_remote_execution_intents SET state = %s, updated_at = now()
           WHERE tenant_id = %s AND request_id = %s AND state = %s
           RETURNING request_id""",
        (target.value, tenant_id, request_id, current.value))
    row = cursor.fetchone()
    if row is None:
        raise TransitionDenied("missing intent or concurrent state change")
    if str(row[0]) != request_id:
        raise TransitionDenied("unexpected updated intent")
    return target
