import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_postgres import enforce_postgres_identity
from app.hitl_identity_policy import IdentityPolicyDenied

class AtomicIdentityTests(unittest.TestCase):
    def setUp(self):
        self.cursor=MagicMock()
        self.cursor.__enter__.return_value=self.cursor
        self.conn=MagicMock()
        self.conn.__enter__.return_value=self.conn
        self.conn.cursor.return_value=self.cursor
        self.factory=MagicMock(return_value=self.conn)
        self.kw=dict(connection_factory=self.factory,subject="subject-123",
            tenant_id=str(uuid4()),token_id="token-12345",issuer="https://id.example")
    def test_success_uses_one_statement_one_connection(self):
        self.cursor.fetchone.return_value=(True,)
        self.assertTrue(enforce_postgres_identity(**self.kw))
        self.factory.assert_called_once()
        self.cursor.execute.assert_called_once()
        sql,args=self.cursor.execute.call_args.args
        self.assertIn("identity_authority_sync",sql)
        self.assertIn("identity_memberships",sql)
        self.assertIn("identity_revocations",sql)
        self.assertEqual(len(args),9)
    def test_denial_fails_closed(self):
        for result in ((False,),None,(1,)):
            with self.subTest(result=result):
                self.cursor.fetchone.return_value=result
                with self.assertRaises(IdentityPolicyDenied):
                    enforce_postgres_identity(**self.kw)
    def test_db_outage_fails_closed(self):
        self.factory.side_effect=OSError("db unavailable")
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.kw)
    def test_invalid_input_skips_database(self):
        self.kw["token_id"]="short"
        with self.assertRaises(IdentityPolicyDenied):
            enforce_postgres_identity(**self.kw)
        self.factory.assert_not_called()
if __name__=="__main__":
    unittest.main()
