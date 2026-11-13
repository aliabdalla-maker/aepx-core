import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_postgres import enforce_postgres_identity
from app.hitl_identity_policy import IdentityPolicyDenied

class PostgresIdentityTests(unittest.TestCase):
    def setUp(self):
        self.conn=MagicMock()
        self.cur=self.conn.cursor.return_value.__enter__.return_value
        self.factory=MagicMock()
        self.factory.return_value.__enter__.return_value=self.conn
        self.args=dict(connection_factory=self.factory,subject="operator-123",
            tenant_id=str(uuid4()),token_id="jwt-token-123",
            issuer="https://identity.example")
    def test_active_member_and_not_revoked(self):
        self.cur.fetchone.side_effect=[(True,),(True,),(True,),(False,)]
        self.assertTrue(enforce_postgres_identity(**self.args))
        self.assertEqual(self.cur.execute.call_count,4)
    def test_inactive_membership_denied(self):
        self.cur.fetchone.side_effect=[(True,),(False,)]
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
        self.assertEqual(self.cur.execute.call_count,2)
    def test_revoked_token_denied(self):
        self.cur.fetchone.side_effect=[(True,),(True,),(True,),(True,)]
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
    def test_database_outage_denied(self):
        self.cur.execute.side_effect=TimeoutError()
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
    def test_ambiguous_db_decision_denied(self):
        self.cur.fetchone.return_value=(1,)
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
    def test_stale_sync_denied(self):
        self.cur.fetchone.return_value=(False,)
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
        self.assertEqual(self.cur.execute.call_count,1)
    def test_sync_healthy_but_unknown_revocation_denied_on_ambiguous_result(self):
        self.cur.fetchone.side_effect=[(True,),(True,),(True,),(None,)]
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.args)
    def test_missing_factory_denied(self):
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**(self.args|{"connection_factory":None}))
if __name__=="__main__":
    unittest.main()
