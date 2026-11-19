"""Fail-closed transaction context guard for remote MCP intent reservations.

The tenant identifier MUST come from upstream verified OIDC authorization and
tenant membership checks. This module does not authenticate identities.
"""
from uuid import UUID

class UnsafeTenantContext(PermissionError):
    pass

def bind_verified_tenant(cursor, *, verified_tenant_id, expected_runtime_role):
    """Bind tenant to current transaction only; reject unexpected DB identity.

    Call inside a transaction, before reserve_intent. Do not accept either
    argument from a request body or model-generated tool parameters.
    """
    try:
        canonical = str(UUID(verified_tenant_id))
        if canonical != verified_tenant_id:
            raise ValueError("noncanonical UUID")
    except (ValueError, TypeError, AttributeError) as exc:
        raise UnsafeTenantContext("invalid verified tenant identifier") from exc
    if not isinstance(expected_runtime_role, str) or not expected_runtime_role:
        raise UnsafeTenantContext("missing configured runtime role")
    cursor.execute("SELECT current_user, current_setting('row_security')")
    identity = cursor.fetchone()
    if not identity or identity[0] != expected_runtime_role or identity[1] != "on":
        raise UnsafeTenantContext("database role or row security mismatch")
    cursor.execute(
        "SELECT rolbypassrls, rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user")
    role_flags = cursor.fetchone()
    if not role_flags or role_flags[0] is not False or role_flags[1] is not False:
        raise UnsafeTenantContext("runtime role can bypass row-level security")
    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (canonical,))
    actual = cursor.fetchone()
    if not actual or actual[0] != canonical:
        raise UnsafeTenantContext("tenant context binding failed")
    return canonical
