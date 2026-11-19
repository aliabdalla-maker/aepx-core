"""Offline-only fail-closed authorization context contract.

This is a policy gate, NOT a login system or PostgreSQL authentication.
Only a trusted backend may create and sign these contexts; never accept keys
or verified=True flags from clients. No database/network side effects.
"""
import hashlib
import hmac
import json
import re
import time
import uuid

ALLOWED_ACTIONS=frozenset({"iteration.claim","iteration.advance",
                           "iteration.renew","approval.consume","budget.reserve",
                           "budget.settle"})
MAX_TTL_SECONDS=300

class AuthorizationDenied(ValueError):
    pass

def _canonical(claims):
    if not isinstance(claims,dict) or set(claims)!={"tenant_id","principal_id",
          "audience","action","issued_at","expires_at","nonce"}:
        raise AuthorizationDenied("invalid claim fields")
    try:
        tenant=uuid.UUID(claims["tenant_id"])
    except (ValueError,TypeError,AttributeError) as exc:
        raise AuthorizationDenied("invalid tenant") from exc
    if str(tenant)!=claims["tenant_id"] or tenant.version!=4:
        raise AuthorizationDenied("noncanonical tenant")
    for field in ("principal_id","audience","action","nonce"):
        val=claims[field]
        if not isinstance(val,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",val):
            raise AuthorizationDenied("invalid "+field)
    if claims["action"] not in ALLOWED_ACTIONS or claims["audience"]!="aepx-db-controller":
        raise AuthorizationDenied("invalid scope")
    issued,expires=claims["issued_at"],claims["expires_at"]
    if type(issued) is not int or type(expires) is not int:
        raise AuthorizationDenied("timestamps must be integers")
    if expires<=issued or expires-issued>MAX_TTL_SECONDS:
        raise AuthorizationDenied("invalid validity window")
    return json.dumps(claims,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def sign_context(claims,key):
    """Trusted service only: caller must authenticate principal before signing."""
    if not isinstance(key,bytes) or len(key)<32:
        raise AuthorizationDenied("weak key")
    return hmac.new(key,_canonical(claims),hashlib.sha256).hexdigest()

def verify_context(claims,signature,key,tenant_id,principal_id,action,now=None):
    """Pure verification. Replay protection and DB authorization remain external."""
    if not isinstance(key,bytes) or len(key)<32:
        raise AuthorizationDenied("weak key")
    payload=_canonical(claims)
    if not isinstance(signature,str) or not re.fullmatch(r"[0-9a-f]{64}",signature):
        raise AuthorizationDenied("invalid signature")
    if not hmac.compare_digest(
        hmac.new(key,payload,hashlib.sha256).hexdigest(),signature):
        raise AuthorizationDenied("signature mismatch")
    if (claims["tenant_id"]!=tenant_id or claims["principal_id"]!=principal_id
            or claims["action"]!=action):
        raise AuthorizationDenied("scope mismatch")
    clock=int(time.time()) if now is None else now
    if type(clock) is not int or clock<claims["issued_at"] or clock>=claims["expires_at"]:
        raise AuthorizationDenied("expired or not yet valid")
    return True
