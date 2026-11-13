import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_signed_receipt_postgres import verify_receipt_with_postgres
from app.hitl_signed_receipts import ReceiptDenied

class SignedReceiptPostgresIntegration(unittest.TestCase):
    def setUp(self):
        self.secret=b"k"*32
        self.payload=dict(receipt_id="receipt-12345",provider="provider-123",
            tenant_id=str(uuid4()),event_id=str(uuid4()),idempotency_key="idempotency-123",
            state="confirmed",evidence_reference="evidence-12345",issued_at=1000)
        self.body=json.dumps(self.payload).encode()
        self.sig="sha256="+hmac.new(self.secret,self.body,hashlib.sha256).hexdigest()
        self.conn=MagicMock()
        self.cur=self.conn.cursor.return_value.__enter__.return_value
        self.factory=MagicMock()
        self.factory.return_value.__enter__.return_value=self.conn
    def verify(self,**kwargs):
        options=dict(raw_body=self.body,signature=self.sig,secret=self.secret,
            expected_provider="provider-123",connection_factory=self.factory,now_epoch=1005)
        options.update(kwargs)
        return verify_receipt_with_postgres(**options)
    def test_signed_receipt_claims_once(self):
        self.cur.fetchone.return_value=("receipt-12345",)
        self.assertTrue(self.verify()["verified"])
        self.conn.commit.assert_called_once()
    def test_duplicate_claim_denied(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(ReceiptDenied):
            self.verify()
        self.conn.commit.assert_not_called()
    def test_db_failure_denied(self):
        self.cur.execute.side_effect=TimeoutError()
        with self.assertRaises(ReceiptDenied):
            self.verify()
    def test_invalid_signature_never_touches_database(self):
        with self.assertRaises(ReceiptDenied):
            self.verify(signature="sha256="+"0"*64)
        self.factory.assert_not_called()
if __name__=="__main__":
    unittest.main()
