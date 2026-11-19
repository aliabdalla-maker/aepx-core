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


def test_separate_offline_authority_subprocess(tmp_path):
    import json,os,subprocess,sys
    from pathlib import Path
    key=Ed25519PrivateKey.generate()
    private=key.private_bytes(encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,encryption_algorithm=serialization.NoEncryption())
    keyfile=tmp_path/"offline.key"
    keyfile.write_bytes(private)
    keyfile.chmod(0o600)
    pub=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    receipt={"tenant":"alpha","reservation":"res-1","provider":"mock",
             "request_id":"immutable-1","tokens":5,"microusd":50}
    result=subprocess.run([sys.executable,"mock_billing_authority.py"],input=json.dumps(receipt),
        text=True,capture_output=True,timeout=10,
        env={"IDE_MOCK_BILLING_PRIVATE_KEY_FILE":str(keyfile),"PATH":os.getenv("PATH","")})
    assert result.returncode==0,result.stderr
    signed=json.loads(result.stdout)
    verify_independent_receipt(signed["receipt"],signed["signature"],pub)
    with pytest.raises(PermissionError):
        verify_independent_receipt({**receipt,"request_id":"immutable-2"},signed["signature"],pub)
