"""HMAC-authenticated offline provider receipts; verification before ledger mutation.

Test/mock trust boundary only. Production requires provider-signed evidence from an
independent billing API, not a shared local test key.
"""
import hashlib
import hmac
import json
from .recovery25 import reconcile

def canonical_receipt(receipt: dict) -> bytes:
    required={"tenant","reservation","provider","request_id","tokens","microusd"}
    if set(receipt)!=required or any(not isinstance(receipt[k],str) or not receipt[k] for k in ("tenant","reservation","provider","request_id")):
        raise ValueError("Invalid receipt fields")
    if any(type(receipt[k]) is not int or receipt[k]<0 for k in ("tokens","microusd")):
        raise ValueError("Invalid receipt usage")
    if any(len(receipt[k])>128 for k in ("tenant","reservation","provider","request_id")):
        raise ValueError("Receipt field too long")
    return json.dumps(receipt,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()

def sign_mock_receipt(receipt: dict, key: bytes) -> str:
    if len(key)<32:
        raise ValueError("Mock signing key too short")
    return hmac.new(key,canonical_receipt(receipt),hashlib.sha256).hexdigest()

def verify_mock_receipt(receipt: dict, signature: str, key: bytes) -> None:
    if len(key)<32 or not isinstance(signature,str) or len(signature)!=64:
        raise PermissionError("Invalid mock receipt authentication")
    expected=sign_mock_receipt(receipt,key)
    if not hmac.compare_digest(expected,signature):
        raise PermissionError("Mock receipt authentication failed")

def reconcile_mock_receipt(db, tenant: str, receipt: dict, signature: str,
                           key: bytes, *, actor: str) -> None:
    verify_mock_receipt(receipt,signature,key)
    if receipt["tenant"]!=tenant:
        raise PermissionError("Cross-tenant receipt denied")
    reference=receipt["provider"]+":"+receipt["request_id"]
    if len(reference)>160:
        raise ValueError("Provider reference too long")
    reconcile(db,tenant,receipt["reservation"],reference,
              receipt["tokens"],receipt["microusd"],actor=actor)
