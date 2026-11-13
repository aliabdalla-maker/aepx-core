"""Fail-closed offline policy for remote MCP request dispatch.

This is a pure validation boundary. It never sends requests, verifies TLS,
checks JWT signatures, or guarantees provider-side exactly-once effects.
"""
from dataclasses import dataclass
from uuid import UUID
import re

_HASH = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")

class RemoteDispatchDenied(PermissionError):
    pass

@dataclass(frozen=True)
class VerifiedGatewayContext:
    tenant_id: str
    approval_id: str
    action_hash: str
    resource_id: str
    protocol_version: str
    tls_peer_verified: bool
    audience_verified: bool
    resource_authorized: bool
    approval_verified: bool

@dataclass(frozen=True)
class RemoteDispatchIntent:
    tenant_id: str
    approval_id: str
    action_hash: str
    resource_id: str
    protocol_version: str
    idempotency_key: str
    tool_name: str

def validate_remote_dispatch(intent, context):
    if not isinstance(intent, RemoteDispatchIntent) or not isinstance(context, VerifiedGatewayContext):
        raise RemoteDispatchDenied("typed dispatch and trusted gateway context required")
    try:
        tenant = str(UUID(intent.tenant_id))
        approval = str(UUID(intent.approval_id))
        if tenant != intent.tenant_id or approval != intent.approval_id:
            raise ValueError("noncanonical UUID")
    except (ValueError, AttributeError, TypeError) as exc:
        raise RemoteDispatchDenied("invalid tenant or approval identifier") from exc
    if not all(type(v) is bool and v for v in (
        context.tls_peer_verified, context.audience_verified,
        context.resource_authorized, context.approval_verified
    )):
        raise RemoteDispatchDenied("missing verified gateway assertion")
    if not all(isinstance(v, str) and v for v in (
        intent.resource_id, intent.protocol_version, intent.tool_name,
        context.resource_id, context.protocol_version
    )):
        raise RemoteDispatchDenied("missing resource, protocol or tool binding")
    if len(intent.tool_name) > 128 or len(intent.resource_id) > 256:
        raise RemoteDispatchDenied("dispatch identifier too long")
    if not isinstance(intent.action_hash, str) or not _HASH.fullmatch(intent.action_hash):
        raise RemoteDispatchDenied("invalid action digest")
    if not isinstance(intent.idempotency_key, str) or not _TOKEN.fullmatch(intent.idempotency_key):
        raise RemoteDispatchDenied("invalid idempotency key")
    for field in ("tenant_id", "approval_id", "action_hash", "resource_id", "protocol_version"):
        if getattr(intent, field) != getattr(context, field):
            raise RemoteDispatchDenied("gateway binding mismatch: " + field)
    return intent
