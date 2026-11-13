"""Fail-closed OIDC JWT verifier for future HITL API integration.

Requires configured issuer/audience/JWKS URL and a trusted IdP contract.
Never accept roles or tenant membership from unverified request headers.
"""
import os
from urllib.parse import urlparse
from uuid import UUID

from app.hitl_authz import VerifiedPrincipal

class AuthenticationDenied(PermissionError):
    pass

def _settings(env):
    issuer=env.get("HITL_OIDC_ISSUER","").rstrip("/")
    audience=env.get("HITL_OIDC_AUDIENCE","")
    jwks=env.get("HITL_OIDC_JWKS_URL","")
    if not issuer or not audience or not jwks:
        raise AuthenticationDenied("OIDC configuration incomplete")
    i=urlparse(issuer)
    j=urlparse(jwks)
    if i.scheme!="https" or j.scheme!="https" or not i.hostname or not j.hostname:
        raise AuthenticationDenied("HTTPS issuer and JWKS required")
    if (j.hostname!=i.hostname or i.username or i.password or j.username or j.password
        or j.fragment or i.fragment or i.query):
        raise AuthenticationDenied("cross-host JWKS forbidden by default")
    return issuer,audience,jwks

def verify_bearer(authorization, *, env=None, key_client=None, jwt_module=None):
    """Return VerifiedPrincipal after asymmetric signature and claim validation.

    key_client and jwt_module are injectable for isolated tests only.
    Production should use PyJWKClient and PyJWT.
    """
    env=os.environ if env is None else env
    issuer,audience,jwks=_settings(env)
    if not isinstance(authorization,str) or not authorization.startswith("Bearer "):
        raise AuthenticationDenied("bearer token required")
    token=authorization[7:]
    if not token or len(token)>16384 or any(ch.isspace() for ch in token):
        raise AuthenticationDenied("invalid bearer token")
    try:
        if jwt_module is None:
            import jwt as jwt_module
        if key_client is None:
            key_client=jwt_module.PyJWKClient(jwks,cache_jwk_set=True,lifespan=300,timeout=5)
        key=key_client.get_signing_key_from_jwt(token).key
        claims=jwt_module.decode(token,key,algorithms=["RS256"],
                                 issuer=issuer,audience=audience,
                                 options={"require":["exp","iat","nbf","iss","aud","sub"]},
                                 leeway=0)
        subject=claims["sub"]
        tenant=UUID(str(claims["tenant_id"]))
        roles=claims["roles"]
        if not isinstance(subject,str) or not 8<=len(subject)<=128 or subject!=subject.strip():
            raise ValueError("invalid subject")
        if (not isinstance(roles,list) or not 1<=len(roles)<=128
            or not all(isinstance(x,str) and 1<=len(x)<=128 for x in roles)):
            raise ValueError("invalid role claims")
        return VerifiedPrincipal(subject=subject,tenant_id=tenant,
                                 roles=frozenset(roles),issuer=issuer)
    except Exception as exc:
        raise AuthenticationDenied("OIDC token verification failed") from exc
