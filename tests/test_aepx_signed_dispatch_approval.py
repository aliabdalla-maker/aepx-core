"""Offline tests for signed approval scope, expiration and tampering."""
import hashlib
import hmac
import json
import unittest
from scripts.aepx_signed_dispatch_approval import verify_approval,ApprovalDenied

KEY=b"test-only-secret-key-with-32-bytes-minimum"
ENVELOPE={"tenant_id":"tenant-1","request_id":"req-1","lease_fence":4,
          "idempotency_key":"provider_request_0001","expires_at":2000,
          "reviewer_id":"reviewer-1"}

def sign(envelope):
    data=json.dumps(envelope,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")
    return hmac.new(KEY,data,hashlib.sha256).hexdigest()

def check(envelope=None,signature=None,**kwargs):
    item=ENVELOPE if envelope is None else envelope
    return verify_approval(envelope=item,signature=sign(item) if signature is None else signature,
                           verification_key=kwargs.pop("verification_key",KEY),
                           tenant_id=kwargs.pop("tenant_id","tenant-1"),
                           request_id=kwargs.pop("request_id","req-1"),
                           lease_fence=kwargs.pop("lease_fence",4),
                           idempotency_key=kwargs.pop("idempotency_key","provider_request_0001"),
                           now=kwargs.pop("now",1999))

class SignedApprovalTests(unittest.TestCase):
    def test_valid_scoped_envelope(self):
        self.assertTrue(check())
    def test_expired(self):
        with self.assertRaises(ApprovalDenied): check(now=2000)
    def test_cross_tenant_replay(self):
        with self.assertRaises(ApprovalDenied): check(tenant_id="tenant-2")
    def test_cross_request_replay(self):
        with self.assertRaises(ApprovalDenied): check(request_id="req-2")
    def test_stale_fence(self):
        with self.assertRaises(ApprovalDenied): check(lease_fence=5)
    def test_different_provider_idempotency(self):
        with self.assertRaises(ApprovalDenied): check(idempotency_key="provider_request_0002")
    def test_tampering(self):
        modified={**ENVELOPE,"reviewer_id":"reviewer-2"}
        with self.assertRaises(ApprovalDenied): check(envelope=modified,signature=sign(ENVELOPE))
    def test_short_key(self):
        with self.assertRaises(ApprovalDenied): check(verification_key=b"short")
    def test_truthy_bool_fence_rejected(self):
        with self.assertRaises(ApprovalDenied): check(envelope={**ENVELOPE,"lease_fence":True})
if __name__=="__main__": unittest.main()
