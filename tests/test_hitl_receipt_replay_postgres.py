import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_receipt_replay_postgres import postgres_receipt_claimer,ReplayClaimDenied

class ReplayPostgresTests(unittest.TestCase):
    def setUp(self):
        self.conn=MagicMock()
        self.cursor=self.conn.cursor.return_value.__enter__.return_value
        self.factory=MagicMock()
        self.factory.return_value.__enter__.return_value=self.conn
        self.claim=postgres_receipt_claimer(self.factory)
    def test_claim_committed(self):
        self.cursor.fetchone.return_value=("receipt-12345",)
        self.assertTrue(self.claim(provider="provider-123",receipt_id="receipt-12345"))
        self.conn.commit.assert_called_once()
        query,params=self.cursor.execute.call_args.args
        self.assertIn("ON CONFLICT",query)
        self.assertEqual(params,("provider-123","receipt-12345"))
    def test_duplicate_denied(self):
        self.cursor.fetchone.return_value=None
        self.assertFalse(self.claim(provider="provider-123",receipt_id="receipt-12345"))
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()
    def test_db_outage_denied(self):
        self.cursor.execute.side_effect=TimeoutError()
        self.assertFalse(self.claim(provider="provider-123",receipt_id="receipt-12345"))
    def test_invalid_provider_denied(self):
        self.assertFalse(self.claim(provider="x",receipt_id="receipt-12345"))
        self.factory.assert_not_called()
    def test_invalid_receipt_denied(self):
        self.assertFalse(self.claim(provider="provider-123",receipt_id="bad receipt"))
        self.factory.assert_not_called()
    def test_missing_factory_denied(self):
        with self.assertRaises(ReplayClaimDenied):
            postgres_receipt_claimer(None)
if __name__=="__main__":
    unittest.main()
