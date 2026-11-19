"""Fail-closed HITL identity/authorisation boundary.

An upstream authentication adapter MUST verify token signature, issuer, audience,
expiry, tenant membership and role claims before constructing VerifiedPrincipal.
Do not instantiate this class from untrusted HTTP headers or JSON payloads.
"""
from dataclasses import dataclass
from uuid import UUID

class AuthorizationDenied(PermissionError):
    pass

@dataclass(frozen=True)
class VerifiedPrincipal:
    subject: str
    tenant_id: UUID
    roles: frozenset[str]
    issuer: str

    def __post_init__(self):
        if not self.subject or not self.issuer or not isinstance(self.tenant_id,UUID):
            raise ValueError("verified subject, tenant and issuer required")
        if not isinstance(self.roles,frozenset) or not self.roles:
            raise ValueError("verified roles required")

def require_role(principal, *, tenant_id, role):
    if not isinstance(principal,VerifiedPrincipal):
        raise AuthorizationDenied("verified identity required")
    if principal.tenant_id != UUID(str(tenant_id)):
        raise AuthorizationDenied("tenant mismatch")
    if role not in principal.roles:
        raise AuthorizationDenied("required role missing")
    return principal.subject

def authorize_request(principal, *, tenant_id):
    return require_role(principal,tenant_id=tenant_id,role="hitl:request")

def authorize_decision(principal, *, tenant_id, requester_id):
    subject=require_role(principal,tenant_id=tenant_id,role="hitl:approve")
    if subject==requester_id:
        raise AuthorizationDenied("self-approval forbidden")
    return subject

def authorize_consume(principal, *, tenant_id):
    return require_role(principal,tenant_id=tenant_id,role="hitl:execute")
