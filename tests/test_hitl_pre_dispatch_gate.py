import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_pre_dispatch_gate import authorize_hitl_dispatch,DispatchDenied

class PreDispatchGateTests(unittest.TestCase):
    def setUp(self):
        self.kw=dict(connection_factory=MagicMock(),subject="subject-12345",
            tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            token_id="token-12345",issuer="https://identity.example",
            approval_id="approval-123",lease_token="lease-123",
            task_id="task-123",verify_approval=MagicMock(return_value=True),
            verify_lease=MagicMock(return_value=True),
            verify_task=MagicMock(return_value=True))
    @patch("app.hitl_pre_dispatch_gate.enforce_postgres_identity",return_value=True)
    def test_all_authorities_required(self,identity):
        self.assertTrue(authorize_hitl_dispatch(**self.kw))
        identity.assert_called_once()
        for name in ("verify_task","verify_lease","verify_approval"):
            self.kw[name].assert_called_once()
    @patch("app.hitl_pre_dispatch_gate.enforce_postgres_identity",return_value=True)
    def test_every_negative_callback_denies(self,identity):
        for name in ("verify_task","verify_lease","verify_approval"):
            with self.subTest(name=name):
                kw=dict(self.kw)
                kw[name]=MagicMock(return_value=False)
                with self.assertRaises(DispatchDenied):
                    authorize_hitl_dispatch(**kw)
    @patch("app.hitl_pre_dispatch_gate.enforce_postgres_identity",return_value=True)
    def test_truthy_non_boolean_denies(self,identity):
        self.kw["verify_lease"]=MagicMock(return_value=1)
        with self.assertRaises(DispatchDenied):
            authorize_hitl_dispatch(**self.kw)
    @patch("app.hitl_pre_dispatch_gate.enforce_postgres_identity",side_effect=OSError("db down"))
    def test_identity_failure_denies_before_callbacks(self,identity):
        with self.assertRaises(DispatchDenied):
            authorize_hitl_dispatch(**self.kw)
        self.kw["verify_task"].assert_not_called()
    def test_missing_callback_denies(self):
        self.kw["verify_approval"]=None
        with self.assertRaises(DispatchDenied):
            authorize_hitl_dispatch(**self.kw)
if __name__=="__main__":
    unittest.main()
