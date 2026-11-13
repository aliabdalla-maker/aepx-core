import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_dispatcher import dispatch_batch,DispatchDisabled

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tenant=uuid4()
        self.conn=MagicMock()
        self.args={"tenant_id":self.tenant,"worker_id":"trusted-worker"}
    def test_disabled_does_not_claim(self):
        with patch("app.hitl_dispatcher.claim") as claim:
            result=dispatch_batch(self.conn,**self.args)
        self.assertEqual(result["mode"],"dry-run")
        claim.assert_not_called()
    def test_env_flag_alone_does_not_enable(self):
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}),patch("app.hitl_dispatcher.claim") as claim:
            self.assertEqual(dispatch_batch(self.conn,**self.args)["mode"],"dry-run")
        claim.assert_not_called()
    def test_explicit_flag_without_env_still_disabled(self):
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":""}),patch("app.hitl_dispatcher.claim") as claim:
            self.assertEqual(dispatch_batch(self.conn,**self.args,enabled=True)["mode"],"dry-run")
        claim.assert_not_called()
    def test_missing_adapter_denied(self):
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}):
            with self.assertRaises(DispatchDisabled):
                dispatch_batch(self.conn,**self.args,enabled=True)
    def test_delivery_and_settlement(self):
        event=uuid4()
        adapter=MagicMock()
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}),patch("app.hitl_dispatcher.claim",return_value=[(event,"hitl.approval.consumed",{"approval_id":"test"},1)]),patch("app.hitl_dispatcher.settle") as settle:
            result=dispatch_batch(self.conn,**self.args,enabled=True,deliver=adapter)
        self.assertEqual(result["delivered"],1)
        self.assertEqual(adapter.call_args.kwargs["event_id"],str(event))
        self.assertEqual(settle.call_args.kwargs["attempt_number"],1)
        self.assertTrue(settle.call_args.kwargs["delivered"])
    def test_adapter_failure_is_redacted_and_retried(self):
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}),patch("app.hitl_dispatcher.claim",return_value=[(uuid4(),"hitl.approval.consumed",{},2)]),patch("app.hitl_dispatcher.settle") as settle:
            result=dispatch_batch(self.conn,**self.args,enabled=True,deliver=MagicMock(side_effect=RuntimeError("password=secret")))
        self.assertEqual(result["failed"],1)
        self.assertEqual(settle.call_args.kwargs["error"],"delivery adapter failed")
        self.assertFalse(settle.call_args.kwargs["delivered"])
    def test_unapproved_topic_never_delivered(self):
        adapter=MagicMock()
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}),patch("app.hitl_dispatcher.claim",return_value=[(uuid4(),"arbitrary.execute",{},1)]),patch("app.hitl_dispatcher.settle"):
            result=dispatch_batch(self.conn,**self.args,enabled=True,deliver=adapter)
        self.assertEqual(result["failed"],1)
        adapter.assert_not_called()
    def test_settlement_failure_propagates(self):
        with patch.dict(os.environ,{"HITL_DISPATCH_ENABLED":"yes"}),patch("app.hitl_dispatcher.claim",return_value=[(uuid4(),"hitl.approval.consumed",{},1)]),patch("app.hitl_dispatcher.settle",side_effect=PermissionError("expired")):
            with self.assertRaises(PermissionError):
                dispatch_batch(self.conn,**self.args,enabled=True,deliver=MagicMock())
if __name__=="__main__":unittest.main()
