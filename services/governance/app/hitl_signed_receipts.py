"""Verify provider-signed status receipts without performing external effects.

Only use a secret provisioned out-of-band for the configured provider.
Replay protection must use a durable, atomic receipt-ID claim in production.
"""
import hashlib
import hmac
import json
import time
from uuid import UUID

class ReceiptDenied(PermissionError):
    pass

def verify_signed_receipt(*,raw_body,signature,secret,expected_provider,
                          now_epoch=None,max_age_seconds=300,claim_receipt_id=None):
    """Verify exact bytes, freshness and durable replay claim, fail closed."""
    try:
        if (not isinstance(raw_body,bytes) or not 1<=len(raw_body)<=16384
            or not isinstance(secret,bytes) or len(secret)<32
            or not isinstance(signature,str) or len(signature)!=71
            or not signature.startswith("sha256=")
            or not isinstance(max_age_seconds,int) or not 1<=max_age_seconds<=900
            or not isinstance(expected_provider,str) or not expected_provider
            or not callable(claim_receipt_id)):
            raise ReceiptDenied("invalid receipt verification configuration")
        digest=hmac.new(secret,raw_body,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,"sha256="+digest):
            raise ReceiptDenied("invalid receipt signature")
        receipt=json.loads(raw_body)
        if not isinstance(receipt,dict):
            raise ReceiptDenied("invalid receipt")
        required=("receipt_id","provider","tenant_id","event_id","idempotency_key",
                  "state","evidence_reference","issued_at")
        if set(receipt)!=set(required):
            raise ReceiptDenied("unexpected receipt fields")
        if receipt["provider"]!=expected_provider or receipt["state"] not in ("confirmed","failed_safe"):
            raise ReceiptDenied("provider or state mismatch")
        tenant=str(UUID(receipt["tenant_id"]))
        event=str(UUID(receipt["event_id"]))
        if tenant!=receipt["tenant_id"] or event!=receipt["event_id"]:
            raise ReceiptDenied("noncanonical identifier")
        for field in ("receipt_id","idempotency_key","evidence_reference"):
            value=receipt[field]
            if (not isinstance(value,str) or not 8<=len(value)<=128
                or not all(ch.isascii() and (ch.isalnum() or ch in "._:-") for ch in value)):
                raise ReceiptDenied("invalid receipt identifier")
        issued=receipt["issued_at"]
        now=int(time.time()) if now_epoch is None else now_epoch
        if (not isinstance(issued,int) or isinstance(issued,bool)
            or not isinstance(now,int) or isinstance(now,bool)
            or issued>now+30 or now-issued>max_age_seconds):
            raise ReceiptDenied("receipt outside freshness window")
        # Must be a durable atomic unique insert/claim, not an in-memory set.
        if claim_receipt_id(provider=expected_provider,receipt_id=receipt["receipt_id"]) is not True:
            raise ReceiptDenied("receipt already claimed or replay protection unavailable")
        return dict(receipt,verified=True)
    except ReceiptDenied:
        raise
    except Exception as exc:
        raise ReceiptDenied("receipt verification unavailable") from exc
