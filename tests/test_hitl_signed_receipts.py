import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_signed_receipts import verify_signed_receipt,ReceiptDenied

class SignedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.secret=b"s"*32
        self.receipt=dict(receipt_id="receipt-12345",provider="trusted-mcp",
            tenant_id=str(uuid4()),event_id=str(uuid4()),idempotency_key="idempotency-123",
            state="confirmed",evidence_reference="evidence-12345",issued_at=1000)
        self.claims=[]
    def signed(self):
        body=json.dumps(self.receipt,separators=(",",":")).encode()
        sig="sha256="+hmac.new(self.secret,body,hashlib.sha256).hexdigest()
        return body,sig
    def verify(self,**changes):
        body,sig=self.signed()
        args=dict(raw_body=body,signature=sig,secret=self.secret,
            expected_provider="trusted-mcp",now_epoch=1010,
            claim_receipt_id=lambda **kw:self.claims.append(kw) or True)
        args.update(changes)
        return verify_signed_receipt(**args)
    def test_valid(self):
        self.assertTrue(self.verify()["verified"])
        self.assertEqual(len(self.claims),1)
    def test_tampered_signature(self):
        body,sig=self.signed()
        with self.assertRaises(ReceiptDenied):
            self.verify(raw_body=body+b" ")
        self.assertEqual(self.claims,[])
    def test_wrong_provider(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(expected_provider="other")
    def test_expired(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(now_epoch=2000)
    def test_future_timestamp(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(now_epoch=900)
    def test_replay_denied(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(claim_receipt_id=lambda **kw:False)
    def test_missing_replay_backend(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(claim_receipt_id=None)
    def test_unknown_field(self):
        self.receipt["extra"]="untrusted"
        with self.assertRaises(ReceiptDenied):
            self.verify()
    def test_wrong_secret(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(secret=b"x"*32)
if __name__=="__main__":
    unittest.main()
