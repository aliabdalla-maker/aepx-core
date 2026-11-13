import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_execution_receipts import execute_local_once,ExecutionDenied

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cur=self.db.cursor.return_value.__enter__.return_value
        self.event=uuid4()
        self.approval=uuid4()
        self.tenant=uuid4()
        self.effect=MagicMock()
        self.payload={"action_hash":"a"*64,"approval_id":str(self.approval)}
        self.verified=("consumed","a"*64,"approver",True)
        self.kw=dict(tenant_id=self.tenant,event_id=self.event,
                     action_hash="a"*64,tool_name="local.test",
                     apply_local=self.effect,approved=True)
    def test_caller_flag_does_not_bypass_db(self):
        self.cur.fetchone.side_effect=[("hitl.approval.consumed",self.payload),None]
        with self.assertRaises(ExecutionDenied):
            execute_local_once(self.db,**self.kw)
        self.effect.assert_not_called()
    def test_first_execution_applies_once_and_commits(self):
        self.cur.fetchone.side_effect=[
            ("hitl.approval.consumed",self.payload),self.verified,None]
        self.assertEqual(execute_local_once(self.db,**self.kw),"applied")
        self.effect.assert_called_once_with(self.cur)
        self.db.commit.assert_called_once()
        sql=" ".join(c.args[0] for c in self.cur.execute.call_args_list)
        self.assertIn("FOR UPDATE",sql)
        self.assertIn("execution_receipts",sql)
    def test_duplicate_skips_effect(self):
        self.cur.fetchone.side_effect=[
            ("hitl.approval.consumed",self.payload),self.verified,("a"*64,"local.test")]
        self.assertEqual(execute_local_once(self.db,**self.kw),"duplicate")
        self.effect.assert_not_called()
    def test_receipt_mismatch_denied(self):
        self.cur.fetchone.side_effect=[
            ("hitl.approval.consumed",self.payload),self.verified,("a"*64,"different.tool")]
        with self.assertRaises(ExecutionDenied):
            execute_local_once(self.db,**self.kw)
        self.db.rollback.assert_called_once()
    def test_callback_failure_rolls_back(self):
        self.cur.fetchone.side_effect=[
            ("hitl.approval.consumed",self.payload),self.verified,None]
        self.effect.side_effect=RuntimeError("sql failure")
        with self.assertRaises(RuntimeError):
            execute_local_once(self.db,**self.kw)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
    def test_expired_approval_denied(self):
        self.cur.fetchone.side_effect=[
            ("hitl.approval.consumed",self.payload),
            ("consumed","a"*64,"approver",False)]
        with self.assertRaises(ExecutionDenied):
            execute_local_once(self.db,**self.kw)
        self.effect.assert_not_called()
    def test_action_mismatch_denied(self):
        self.cur.fetchone.return_value=("hitl.approval.consumed",{"action_hash":"b"*64})
        with self.assertRaises(ExecutionDenied):
            execute_local_once(self.db,**self.kw)
        self.effect.assert_not_called()
if __name__=="__main__": unittest.main()
