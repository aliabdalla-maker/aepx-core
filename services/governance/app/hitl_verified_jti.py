"""Extract verified JWT identity claims and enforce PostgreSQL authority.

This boundary only accepts claims returned by the trusted JWT decoder.
Do not call with unverified JSON or headers.
"""
from uuid import UUID
from app.hitl_identity_postgres import enforce_postgres_identity
from app.hitl_identity_policy import IdentityPolicyDenied

def enforce_verified_claims_identity(*, verified_claims, connection_factory, expected_tenant):
    if not isinstance(verified_claims,dict):
        raise IdentityPolicyDenied("verified claims required")
    try:
        subject=verified_claims["sub"]
        issuer=verified_claims["iss"]
        token_id=verified_claims["jti"]
        tenant=UUID(str(verified_claims["tenant_id"]))
        if (not isinstance(subject,str) or not 8<=len(subject)<=128
            or not isinstance(issuer,str) or not issuer.startswith("https://")
            or not isinstance(token_id,str) or not 8<=len(token_id)<=256
            or tenant!=UUID(str(expected_tenant))):
            raise ValueError("identity claim mismatch")
        return enforce_postgres_identity(connection_factory=connection_factory,
            subject=subject,tenant_id=tenant,token_id=token_id,issuer=issuer)
    except IdentityPolicyDenied:
        raise
    except Exception as exc:
        raise IdentityPolicyDenied("verified identity claims incomplete") from exc
