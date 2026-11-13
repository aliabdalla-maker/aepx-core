import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_replay import find_matching_replay
from app.hitl_postgres import fingerprint

class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tenant=uuid4()
        self.approval=uuid4()
        self.action={"kind":"read"}
        self.payload={"approval_id":str(self.approval),"action_hash":fingerprint(self.action),"actor_id":"worker"}
        self.conn=MagicMock()
        self.cursor=self.conn.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value=("event-id",self.payload)
    def lookup(self,**changes):
        args=dict(tenant_id=self.tenant,approval_id=self.approval,action=self.action,idempotency_key="key-12345",actor_id="worker")
        args.update(changes)
        return find_matching_replay(self.conn,**args)
    def test_matching_replay(self):
        self.assertEqual(self.lookup(),"event-id")
    def test_different_actor_denied(self):
        self.assertIsNone(self.lookup(actor_id="other"))
    def test_different_action_denied(self):
        self.assertIsNone(self.lookup(action={"kind":"write"}))
    def test_different_approval_denied(self):
        self.assertIsNone(self.lookup(approval_id=uuid4()))
    def test_no_row_denied(self):
        self.cursor.fetchone.return_value=None
        self.assertIsNone(self.lookup())
    def test_transaction_cleared(self):
        self.lookup()
        self.conn.rollback.assert_called_once()
    def test_sql_is_tenant_scoped(self):
        self.lookup()
        sql=self.cursor.execute.call_args_list[1].args[0]
        self.assertIn("tenant_id=%s",sql)
        self.assertIn("idempotency_key=%s",sql)
if __name__=="__main__":unittest.main()
