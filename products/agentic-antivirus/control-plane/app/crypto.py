"""Signing (Ed25519) for policies, commands and update bundles; token hashing; passwords.

Trace: RSP-08 (signed commands), OPS-02 (signed updates/policies), ARC-02, BE-09.
The private key is loaded from a mounted file (runtime secret store). With no key file
configured the control plane refuses to sign (fail closed) rather than generating one,
except in tests, which inject a key explicitly.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import settings

_ph = PasswordHasher()
_key: Ed25519PrivateKey | None = None


def set_signing_key(key: Ed25519PrivateKey) -> None:
    global _key
    _key = key


def _signing_key() -> Ed25519PrivateKey:
    global _key
    if _key is None:
        if not settings.signing_key_file:
            raise RuntimeError("AAV_SIGNING_KEY_FILE not configured; refusing to sign")
        with open(settings.signing_key_file, "rb") as fh:
            loaded = serialization.load_pem_private_key(fh.read(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise RuntimeError("signing key must be Ed25519")
        _key = loaded
    return _key


def public_key_pem() -> str:
    return _signing_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def key_id() -> str:
    raw = _signing_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(obj) -> str:
    return base64.b64encode(_signing_key().sign(canonical(obj))).decode()


def verify(obj, signature_b64: str, public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(base64.b64decode(signature_b64), canonical(obj))
        return True
    except Exception:
        return False


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    if not stored:
        _ph.hash(password)  # equalise timing for accounts without a password
        return False
    try:
        return _ph.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hmac_ok(secret_hash: str, presented_secret: str) -> bool:
    return hmac.compare_digest(secret_hash, token_hash(presented_secret))
