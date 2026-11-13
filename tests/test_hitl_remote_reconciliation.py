import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_remote_reconciliation import (
    reserve_remote,reconcile_remote,ReconciliationRequired)

class RemoteReceiptTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cur=self.db.cursor.return_value.__enter__.return_value
        self.kw=dict(tenant_id=uuid4(),event_id=uuid4(),provider="trusted-mcp",
                     idempotency_key="event-key-123456")
    def test_reservation_commits_uncertain_before_external_call(self):
        self.cur.fetchone.side_effect=[("hitl.approval.consumed",),(str(self.kw["event_id"]),)]
        self.assertEqual(reserve_remote(self.db,**self.kw)["state"],"uncertain")
        self.db.commit.assert_called_once()
        sql=" ".join(c.args[0] for c in self.cur.execute.call_args_list)
        self.assertIn("FOR UPDATE",sql)
        self.assertIn("ON CONFLICT",sql)
    def test_duplicate_reservation_rejected(self):
        self.cur.fetchone.side_effect=[("hitl.approval.consumed",),None]
        with self.assertRaises(ReconciliationRequired):
            reserve_remote(self.db,**self.kw)
        self.db.rollback.assert_called_once()
    def test_wrong_topic_denied(self):
        self.cur.fetchone.return_value=("unapproved.topic",)
        with self.assertRaises(ReconciliationRequired):
            reserve_remote(self.db,**self.kw)
    def test_reconcile_requires_authorization(self):
        with self.assertRaises(ReconciliationRequired):
            reconcile_remote(self.db,**self.kw,verified_state="confirmed",
                             evidence_reference="provider-proof-123",reviewer_id="reviewer-123")
        self.db.cursor.assert_not_called()
    def test_uncertain_cannot_be_declared_success_without_evidence(self):
        with self.assertRaises(ValueError):
            reconcile_remote(self.db,**self.kw,verified_state="confirmed",
                             evidence_reference="",reviewer_id="reviewer-123",authorized=True)
    def test_reconcile_writes_audit_in_same_transaction(self):
        self.cur.fetchone.return_value=(str(self.kw["event_id"]),)
        self.cur.rowcount=1
        result=reconcile_remote(self.db,**self.kw,verified_state="confirmed",
             evidence_reference="provider-proof-123",reviewer_id="reviewer-123",authorized=True)
        self.assertEqual(result["state"],"confirmed")
        self.db.commit.assert_called_once()
        sql=" ".join(c.args[0] for c in self.cur.execute.call_args_list)
        self.assertIn("hitl.events",sql)
    def test_audit_failure_rolls_back(self):
        self.cur.fetchone.return_value=(str(self.kw["event_id"]),)
        self.cur.rowcount=0
        with self.assertRaises(ReconciliationRequired):
            reconcile_remote(self.db,**self.kw,verified_state="failed_safe",
                 evidence_reference="provider-proof-123",reviewer_id="reviewer-123",authorized=True)
        self.db.rollback.assert_called_once()
if __name__=="__main__":unittest.main()
