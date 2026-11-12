"""Offline cryptographic billing authority and replay protections."""
import base64
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from app.billing29 import canonical_receipt
from app.billing211 import verify_independent_receipt,reconcile_independent_receipt

def test_independent_authority_signature_and_tamper():
    key=Ed25519PrivateKey.generate()
    pub=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                      format=serialization.PublicFormat.Raw)
    receipt={"tenant":"alpha","reservation":"r1","provider":"offline-mock",
             "request_id":"immutable-request-1","tokens":4,"microusd":40}
    sig=base64.b64encode(key.sign(canonical_receipt(receipt))).decode()
    verify_independent_receipt(receipt,sig,pub)
    with pytest.raises(PermissionError):
        verify_independent_receipt({**receipt,"microusd":41},sig,pub)
    with pytest.raises(PermissionError):
        verify_independent_receipt(receipt,sig,Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw))
    with pytest.raises(PermissionError):
        verify_independent_receipt(receipt,"invalid",pub)
    with pytest.raises(PermissionError):
        reconcile_independent_receipt(None,"beta",receipt,sig,pub,actor="offline")
