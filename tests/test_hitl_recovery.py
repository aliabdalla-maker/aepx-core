import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_recovery import requeue_dead_letter,RecoveryDenied

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cur=self.db.cursor.return_value.__enter__.return_value
        self.tenant=uuid4()
        self.event=uuid4()
        self.kw=dict(tenant_id=self.tenant,event_id=self.event,operator_id="security-operator",
                     ticket_id="INC-123456",reason="reviewed downstream event deduplication",
                     approved=True,idempotency_verified=True)
    def test_denied_without_both_approvals(self):
        for flag in ("approved","idempotency_verified"):
            with self.subTest(flag=flag):
                args=dict(self.kw,**{flag:False})
                with self.assertRaises(RecoveryDenied):
                    requeue_dead_letter(self.db,**args)
        self.db.cursor.assert_not_called()
    def test_requeue_is_audited_atomically(self):
        self.cur.fetchone.return_value=(str(self.event),)
        result=requeue_dead_letter(self.db,**self.kw)
        self.assertEqual(result["status"],"pending")
        self.db.commit.assert_called_once()
        sql=" ".join(c.args[0] for c in self.cur.execute.call_args_list)
        self.assertIn("status='dead'",sql)
        self.assertIn("outbox_recovery_audit",sql)
        self.assertIn("set_config('app.tenant_id'",sql)
    def test_non_dead_rejected_and_rolled_back(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(RecoveryDenied):
            requeue_dead_letter(self.db,**self.kw)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
    def test_audit_failure_rolls_back_requeue(self):
        self.cur.fetchone.return_value=(str(self.event),)
        self.cur.execute.side_effect=[None,None,RuntimeError("audit unavailable")]
        with self.assertRaises(RuntimeError):
            requeue_dead_letter(self.db,**self.kw)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
    def test_invalid_reason_rejected_before_db(self):
        with self.assertRaises(ValueError):
            requeue_dead_letter(self.db,**dict(self.kw,reason="short"))
        self.db.cursor.assert_not_called()
if __name__=="__main__":unittest.main()
