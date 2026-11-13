"""Cryptographic JWT entrypoint for authoritative HITL identity checks.

Unlike the internal verified-claims adapter, this function accepts a bearer
token and validates its signature, issuer, audience and required claims.
"""
import os
from app.hitl_identity_policy import IdentityPolicyDenied
from app.hitl_verified_jti import enforce_verified_claims_identity

def verify_bearer_identity(authorization, *, expected_tenant, connection_factory,
                           env=None, key_client=None, jwt_module=None):
    settings=os.environ if env is None else env
    if not isinstance(authorization,str) or not authorization.startswith("Bearer "):
        raise IdentityPolicyDenied("bearer token required")
    token=authorization[7:]
    if not token or len(token)>16384 or any(ch.isspace() for ch in token):
        raise IdentityPolicyDenied("invalid bearer token")
    try:
        # Import lazily to permit security-regression tests with injected decoder.
        from app.hitl_oidc import _settings
        issuer,audience,jwks=_settings(settings)
        if jwt_module is None:
            import jwt as jwt_module
        if key_client is None:
            key_client=jwt_module.PyJWKClient(
                jwks,cache_jwk_set=True,lifespan=300,timeout=5)
        key=key_client.get_signing_key_from_jwt(token).key
        claims=jwt_module.decode(token,key,algorithms=["RS256"],
            issuer=issuer,audience=audience,leeway=0,
            options={"require":["exp","iat","nbf","iss","aud","sub","jti","tenant_id"]})
        if not isinstance(claims,dict) or claims.get("iss")!=issuer:
            raise ValueError("issuer mismatch")
        return enforce_verified_claims_identity(
            verified_claims=claims,connection_factory=connection_factory,
            expected_tenant=expected_tenant)
    except Exception as exc:
        raise IdentityPolicyDenied("cryptographic identity verification denied") from exc
