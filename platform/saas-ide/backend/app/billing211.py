"""Independent offline mock billing verification.

The billing authority is a separate process holding an Ed25519 private key.
This consumer accepts only its pinned public key, never a caller-provided
signing secret. Production providers need their own independently verified API.
"""
import base64
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .billing29 import canonical_receipt
from .recovery25 import reconcile

def verify_independent_receipt(receipt: dict, signature_b64: str, public_key: bytes):
    if len(public_key)!=32 or not isinstance(signature_b64,str):
        raise PermissionError("Invalid billing authority")
    try:
        signature=base64.b64decode(signature_b64,validate=True)
        if len(signature)!=64:
            raise ValueError("Invalid signature length")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature,canonical_receipt(receipt))
    except (ValueError,TypeError,Exception) as exc:
        # Never include receipt or key in error messages.
        raise PermissionError("Untrusted provider receipt") from None

def reconcile_independent_receipt(db,tenant,receipt,signature_b64,public_key,*,actor):
    verify_independent_receipt(receipt,signature_b64,public_key)
    if receipt["tenant"]!=tenant:
        raise PermissionError("Cross-tenant receipt")
    # Database unique provider_reference prevents reuse across reservations.
    ref=receipt["provider"]+":"+receipt["request_id"]
    if len(ref)>160:
        raise ValueError("Provider request reference too long")
    return reconcile(db,tenant,receipt["reservation"],ref,receipt["tokens"],receipt["microusd"],actor=actor)
