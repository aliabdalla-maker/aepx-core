"""Fail-closed RBAC adapter for already-verified OIDC identity claims.

This module does not validate JWT signatures. The upstream trusted identity
middleware MUST verify issuer, audience, signature, expiry and revocation.
Never pass raw client claims or unverified decoded tokens.
"""
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class VerifiedOperator:
    subject: str
    tenant_id: str
    issuer: str
    audience: str
    permissions: frozenset[str]
    authenticated: bool
    expires_at: int

def operator_verifier(operator,*,trusted_issuer,trusted_audience,now_epoch):
    """Return an injectable verifier for reconcile_remote; deny by default."""
    def verify(*,tenant_id,event_id,provider,reviewer_id,permission,verified_state):
        if not isinstance(operator,VerifiedOperator) or operator.authenticated is not True:
            return False
        if not isinstance(now_epoch,int) or isinstance(now_epoch,bool):
            return False
        if operator.issuer!=trusted_issuer or operator.audience!=trusted_audience:
            return False
        if not trusted_issuer or not trusted_audience:
            return False
        if not isinstance(operator.expires_at,int) or operator.expires_at<=now_epoch:
            return False
        if not isinstance(operator.permissions,frozenset):
            return False
        if operator.subject!=reviewer_id or permission not in operator.permissions:
            return False
        if permission!="hitl.remote.reconcile" or verified_state not in ("confirmed","failed_safe"):
            return False
        try:
            return (str(UUID(operator.tenant_id))==str(UUID(tenant_id))
                    and str(UUID(event_id))!=str(UUID(int=0))
                    and isinstance(provider,str) and bool(provider.strip()))
        except (ValueError,TypeError,AttributeError):
            return False
    return verify
