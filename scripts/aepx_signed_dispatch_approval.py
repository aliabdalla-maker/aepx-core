"""Offline HMAC approval envelope verification, not a production identity service.

The key must be provisioned by a trusted operator. The verifier cannot prove
human identity, revoke keys, or establish durable single-use authorization.
"""
import hashlib
import hmac
import json
import re
import time

FIELDS=("tenant_id","request_id","lease_fence","idempotency_key","expires_at","reviewer_id")
ID=re.compile(r"^[A-Za-z0-9_-]{1,128}$")
KEY=re.compile(r"^[A-Za-z0-9_-]{16,128}$")
SIGNATURE=re.compile(r"^[0-9a-f]{64}$")

class ApprovalDenied(ValueError):
    pass

def _payload(envelope):
    if not isinstance(envelope,dict) or set(envelope)!=set(FIELDS):
        raise ApprovalDenied("invalid approval envelope")
    if any(not isinstance(envelope[k],str) or not ID.fullmatch(envelope[k])
           for k in ("tenant_id","request_id","reviewer_id")):
        raise ApprovalDenied("invalid approval identity")
    if not isinstance(envelope["idempotency_key"],str) or not KEY.fullmatch(envelope["idempotency_key"]):
        raise ApprovalDenied("invalid idempotency key")
    if type(envelope["lease_fence"]) is not int or envelope["lease_fence"] <= 0:
        raise ApprovalDenied("invalid fence")
    if type(envelope["expires_at"]) is not int or envelope["expires_at"] <= 0:
        raise ApprovalDenied("invalid expiration")
    return json.dumps(envelope,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def verify_approval(*, envelope, signature, verification_key, tenant_id,
                    request_id, lease_fence, idempotency_key, now=None):
    """Verify a scoped, expiring HMAC-SHA256 envelope without external calls."""
    payload=_payload(envelope)
    if not isinstance(verification_key,bytes) or len(verification_key)<32:
        raise ApprovalDenied("verification key unavailable")
    if not isinstance(signature,str) or not SIGNATURE.fullmatch(signature):
        raise ApprovalDenied("invalid approval signature")
    if (envelope["tenant_id"]!=tenant_id or envelope["request_id"]!=request_id or
        envelope["lease_fence"]!=lease_fence or envelope["idempotency_key"]!=idempotency_key):
        raise ApprovalDenied("approval scope mismatch")
    current=int(time.time()) if now is None else now
    if type(current) is not int or current < 0 or current >= envelope["expires_at"]:
        raise ApprovalDenied("expired or invalid approval time")
    expected=hmac.new(verification_key,payload,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):
        raise ApprovalDenied("approval signature mismatch")
    return True
