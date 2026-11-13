import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_dispatcher import dispatch_batch

TENANT = "11111111-1111-4111-8111-111111111111"
EVENT = "22222222-2222-4222-8222-222222222222"

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.lease_patch = patch("app.hitl_dispatcher.lease_is_current", return_value=True)
        self.lease_check = self.lease_patch.start()
        self.addCleanup(self.lease_patch.stop)
        self.db = MagicMock()
        self.deliver = MagicMock()
        self.kw = dict(connection=self.db, tenant_id=TENANT,
                       worker_id="worker-1", deliver=self.deliver, enabled=True)
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    def test_invalid_retry_and_batch_fail_before_claim(self):
        for key, value in (("retry_seconds", 0), ("retry_seconds", 86401),
                           ("limit", 0), ("limit", True),
                           ("lease_seconds", 0), ("max_attempts", 0),
                           ("max_batch_seconds", 60), ("max_batch_seconds", 0)):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    dispatch_batch(**dict(self.kw, **{key: value}))
        self.deliver.assert_not_called()
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_invalid_fencing_token_never_delivers(self, reap, claim):
        claim.return_value = [(EVENT, "hitl.approval.consumed", {}, 0)]
        with self.assertRaises(ValueError):
            dispatch_batch(**self.kw)
        self.deliver.assert_not_called()
    def test_dry_run_even_with_adapter_and_flag_off(self):
        with patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"}):
            self.assertEqual(dispatch_batch(**dict(self.kw, enabled=False))["mode"], "dry-run")
        self.deliver.assert_not_called()
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.time.monotonic", side_effect=[100.0, 131.0])
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_expired_batch_defers_without_delivery(self, reap, claim, clock):
        claim.return_value = [(EVENT, "hitl.approval.consumed", {}, 1)]
        result = dispatch_batch(**self.kw)
        self.assertEqual(result["deferred"], 1)
        self.deliver.assert_not_called()
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.settle")
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_expired_lease_never_invokes_adapter(self, reap, claim, settle):
        claim.return_value = [(EVENT, "hitl.approval.consumed", {}, 1)]
        self.lease_check.return_value = False
        result = dispatch_batch(**self.kw)
        self.deliver.assert_not_called()
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["stale"], 1)
        settle.assert_not_called()
    def test_default_dry_run(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(dispatch_batch(**self.kw)["mode"], "dry-run")
        self.deliver.assert_not_called()
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.settle")
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_delivers_and_fences(self, reap, claim, settle):
        claim.return_value = [(EVENT, "hitl.approval.consumed", {}, 1)]
        result = dispatch_batch(**self.kw)
        self.assertEqual(result["delivered"], 1)
        self.assertTrue(settle.call_args.kwargs["delivered"])
        self.assertEqual(settle.call_args.kwargs["attempt_number"], 1)
        reap.assert_called_once()
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.settle")
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_unapproved_topic_retried(self, reap, claim, settle):
        claim.return_value = [(EVENT, "untrusted", {}, 2)]
        self.assertEqual(dispatch_batch(**self.kw)["failed"], 1)
        self.deliver.assert_not_called()
        self.assertFalse(settle.call_args.kwargs["delivered"])
        self.assertGreaterEqual(settle.call_args.kwargs["retry_seconds"], 60)
        self.assertLessEqual(settle.call_args.kwargs["retry_seconds"], 70)
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    @patch("app.hitl_dispatcher.settle", side_effect=PermissionError("stale"))
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted", return_value=[])
    def test_stale_lease_not_overwritten(self, reap, claim, settle):
        claim.return_value = [(EVENT, "hitl.approval.consumed", {}, 3)]
        self.assertEqual(dispatch_batch(**self.kw)["stale"], 1)
    @patch.dict(os.environ, {"HITL_DISPATCH_ENABLED": "yes"})
    def test_requires_adapter(self):
        with self.assertRaises(PermissionError):
            dispatch_batch(**dict(self.kw, deliver=None))

if __name__ == "__main__":
    unittest.main()
