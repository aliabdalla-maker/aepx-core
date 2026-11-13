"""Cryptographically validate OIDC JWTs before creating trusted HITL operators.

Use a trusted, pinned HTTPS JWKS endpoint and issuer/audience configuration.
This module never accepts unsigned tokens, caller-supplied keys or algorithms.
"""
import time
from uuid import UUID
import jwt
from jwt import PyJWKClient
from .hitl_operator_identity import VerifiedOperator

class IdentityVerificationError(PermissionError):
    pass

def verify_oidc_operator(token,*,issuer,audience,jwks_url,tenant_claim="tenant_id",
                         permission_claim="permissions",now_epoch=None,jwk_client=None):
    if not isinstance(token,str) or not token or len(token)>16384:
        raise IdentityVerificationError("invalid identity token")
    if (not isinstance(issuer,str) or not issuer.startswith("https://")
        or not isinstance(audience,str) or not audience
        or not isinstance(jwks_url,str) or not jwks_url.startswith("https://")):
        raise IdentityVerificationError("trusted HTTPS OIDC configuration required")
    # Never derive a JWKS URL, issuer, audience or algorithm from JWT headers.
    try:
        client=jwk_client if jwk_client is not None else PyJWKClient(
            jwks_url,cache_jwk_set=True,lifespan=300,timeout=5)
        signing_key=client.get_signing_key_from_jwt(token)
        claims=jwt.decode(token,signing_key.key,algorithms=["RS256"],
                          audience=audience,issuer=issuer,
                          options={"require":["exp","iat","nbf","iss","aud","sub"]},
                          leeway=0)
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
