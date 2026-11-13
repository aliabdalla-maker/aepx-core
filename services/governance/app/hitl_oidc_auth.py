"""Cryptographically validate OIDC JWTs before creating trusted HITL operators.

Use a trusted, pinned HTTPS JWKS endpoint and issuer/audience configuration.
This module never accepts unsigned tokens, caller-supplied keys or algorithms.
"""
import time
from urllib.parse import urlparse
from uuid import UUID
import jwt
from jwt import PyJWKClient
from .hitl_operator_identity import VerifiedOperator

class IdentityVerificationError(PermissionError):
    pass

def verify_oidc_operator(token,*,issuer,audience,jwks_url,tenant_claim="tenant_id",
                         permission_claim="permissions",now_epoch=None,jwk_client=None):
    if (not isinstance(token,str) or not token or len(token)>16384
        or any(ch.isspace() for ch in token)):
        raise IdentityVerificationError("invalid identity token")
    if (not isinstance(issuer,str) or not issuer.startswith("https://")
        or not isinstance(audience,str) or not audience
        or not isinstance(jwks_url,str) or not jwks_url.startswith("https://")):
        raise IdentityVerificationError("trusted HTTPS OIDC configuration required")
    issuer_location=urlparse(issuer)
    jwks_location=urlparse(jwks_url)
    if (not issuer_location.hostname or not jwks_location.hostname
        or issuer_location.hostname!=jwks_location.hostname
        or issuer_location.username or issuer_location.password
        or jwks_location.username or jwks_location.password
        or jwks_location.fragment or issuer_location.fragment or issuer_location.query):
        raise IdentityVerificationError("untrusted JWKS location")
    try:
        from .hitl_jwt_shared import decode_verified_jwt
        claims=decode_verified_jwt(token,issuer=issuer,audience=audience,
            jwks_url=jwks_url,key_client=jwk_client)
        subject=claims["sub"]
        tenant=str(UUID(str(claims[tenant_claim])))
        permissions=claims[permission_claim]
        if (not isinstance(subject,str) or not 8<=len(subject)<=128
            or not isinstance(permissions,list) or len(permissions)>128
            or not all(isinstance(p,str) and 1<=len(p)<=128 for p in permissions)):
            raise ValueError("invalid subject or permission claims")
        exp=claims["exp"]
        if not isinstance(exp,int) or isinstance(exp,bool):
            raise ValueError("invalid expiry")
        now=int(time.time()) if now_epoch is None else now_epoch
        if not isinstance(now,int) or isinstance(now,bool) or exp<=now:
            raise ValueError("expired token")
        return VerifiedOperator(subject=subject,tenant_id=tenant,issuer=issuer,
            audience=audience,permissions=frozenset(permissions),
            authenticated=True,expires_at=exp)
    except (jwt.PyJWTError,KeyError,TypeError,ValueError,AttributeError) as exc:
        raise IdentityVerificationError("OIDC identity verification failed") from exc
