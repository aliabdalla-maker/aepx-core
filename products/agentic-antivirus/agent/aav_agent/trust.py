"""Signature verification against the control-plane key pinned at enrolment (RSP-08, OPS-02)."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class Verifier:
    def __init__(self, public_key_pem: str):
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("pinned key must be Ed25519")
        self.key = key

    def ok(self, obj, signature_b64: str) -> bool:
        try:
            self.key.verify(base64.b64decode(signature_b64), canonical(obj))
            return True
        except Exception:
            return False


def not_expired(iso: str) -> bool:
    return datetime.fromisoformat(iso) > datetime.now(timezone.utc)
