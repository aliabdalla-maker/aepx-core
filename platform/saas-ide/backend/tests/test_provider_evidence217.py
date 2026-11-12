"""Synthetic Ed25519 provider receipts; no network or paid API calls."""
import base64
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from app.provider_evidence217 import verify_signed_receipt

def test_signed_receipt_valid_and_tampering_rejected(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY", base64.b64encode(public).decode())
    fields = {"tenant": "alpha", "run_id": "run-1", "approval_id": "approval-1",
              "outcome": "succeeded", "reference": "provider-operation-123"}
    def signed(data):
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        receipt = dict(data, signature=base64.b64encode(private.sign(payload)).decode())
        return base64.urlsafe_b64encode(json.dumps(receipt).encode()).decode().rstrip("=")
    receipt = signed(fields)
    assert verify_signed_receipt("alpha", "run-1", "approval-1", "succeeded", receipt)
    for tenant, run, approval, outcome in [
        ("beta", "run-1", "approval-1", "succeeded"),
        ("alpha", "run-2", "approval-1", "succeeded"),
        ("alpha", "run-1", "approval-2", "succeeded"),
        ("alpha", "run-1", "approval-1", "failed"),
    ]:
        assert not verify_signed_receipt(tenant, run, approval, outcome, receipt)
    altered = json.loads(base64.urlsafe_b64decode(receipt + "=" * (-len(receipt) % 4)))
    altered["outcome"] = "failed"
    forged = base64.urlsafe_b64encode(json.dumps(altered).encode()).decode().rstrip("=")
    assert not verify_signed_receipt("alpha", "run-1", "approval-1", "failed", forged)
    monkeypatch.delenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY")
    assert not verify_signed_receipt("alpha", "run-1", "approval-1", "succeeded", receipt)
