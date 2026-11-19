"""Shared, fail-closed OIDC JWT verification primitive for HITL boundaries."""
from urllib.parse import urlparse
import jwt

class TokenVerificationDenied(PermissionError):
    pass

def validate_oidc_settings(issuer,audience,jwks_url):
    if not all(isinstance(v,str) and v for v in (issuer,audience,jwks_url)):
        raise TokenVerificationDenied("OIDC configuration incomplete")
    i=urlparse(issuer)
    j=urlparse(jwks_url)
    if (i.scheme!="https" or j.scheme!="https" or not i.hostname or not j.hostname
        or i.hostname!=j.hostname or i.username or i.password or j.username
        or j.password or i.query or i.fragment or j.fragment):
        raise TokenVerificationDenied("untrusted OIDC configuration")
    return issuer,audience,jwks_url

def decode_verified_jwt(token,*,issuer,audience,jwks_url,key_client=None,jwt_module=None):
    validate_oidc_settings(issuer,audience,jwks_url)
    if (not isinstance(token,str) or not token or len(token)>16384
        or any(ch.isspace() for ch in token)):
        raise TokenVerificationDenied("invalid bearer token")
    jwt_impl=jwt if jwt_module is None else jwt_module
    try:
        client=key_client if key_client is not None else jwt_impl.PyJWKClient(
            jwks_url,cache_jwk_set=True,lifespan=300,timeout=5)
        key=client.get_signing_key_from_jwt(token).key
        claims=jwt_impl.decode(token,key,algorithms=["RS256"],
            issuer=issuer,audience=audience,
            options={"require":["exp","iat","nbf","iss","aud","sub"]},
            leeway=0)
        if not isinstance(claims,dict):
            raise ValueError("invalid claims")
        return claims
    except Exception as exc:
        raise TokenVerificationDenied("OIDC signature or claims verification failed") from exc
