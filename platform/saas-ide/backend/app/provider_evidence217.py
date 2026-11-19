"""Offline verification of independently signed provider reconciliation receipts.

Provider public key is configured out-of-band; private keys never enter AEP-X.
No network calls, secrets, or live provider operations occur in this module.
"""
import base64
import json
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

def verify_signed_receipt(tenant: str, run_id: str, approval_id: str,
                          outcome: str, evidence_reference: str) -> bool:
    """Verify base64url JSON receipt with detached Ed25519 signature.

    Receipt fields: tenant, run_id, approval_id, outcome, reference, signature.
    Signed bytes are canonical JSON of the five non-signature fields.
    """
    if outcome not in ("succeeded", "failed") or len(evidence_reference) > 4096:
        return False
    public_key = os.getenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY", "")
    if not public_key:
        return False
    try:
        raw = base64.urlsafe_b64decode(evidence_reference + "=" * (-len(evidence_reference) % 4))
        if len(raw) > 3072:
            return False
        receipt = json.loads(raw)
        fields = ("tenant", "run_id", "approval_id", "outcome", "reference")
        if not isinstance(receipt, dict) or set(receipt) != set(fields) | {"signature"}:
            return False
        expected = (tenant, run_id, approval_id, outcome)
        if tuple(receipt[k] for k in fields[:4]) != expected:
            return False
        if not isinstance(receipt["reference"], str) or not 1 <= len(receipt["reference"]) <= 160:
            return False
        signature = base64.b64decode(receipt["signature"], validate=True)
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        payload = json.dumps({k: receipt[k] for k in fields}, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=True).encode()
        key.verify(signature, payload)
        return True
    except (ValueError, TypeError, KeyError, UnicodeError):
        return False
    except Exception:
        return False
