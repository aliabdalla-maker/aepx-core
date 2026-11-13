import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_dispatcher import dispatch_once

TENANT = "11111111-1111-4111-8111-111111111111"
EVENT = "22222222-2222-4222-8222-222222222222"

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.connect = MagicMock()
        self.effect = MagicMock()
        self.args = dict(connect=self.connect, tenant_id=TENANT,
                         worker_id="worker-1", apply_local=self.effect)
    @patch("app.hitl_dispatcher.execute_local_once", return_value="applied")
    @patch("app.hitl_dispatcher.settle")
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted")
    def test_delivers_local_once(self, reap, claim, settle, execute):
        claim.return_value = [(EVENT, "hitl.approval.consumed",
                               {"action_hash": "a"*64}, 1)]
        self.assertEqual(dispatch_once(**self.args), [(EVENT, "delivered")])
        self.assertTrue(settle.call_args.kwargs["delivered"])
        self.assertEqual(settle.call_args.kwargs["attempt_number"], 1)
        self.assertEqual(execute.call_count, 1)
        reap.assert_called_once()
    @patch("app.hitl_dispatcher.execute_local_once")
    @patch("app.hitl_dispatcher.settle")
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted")
    def test_unsupported_topic_fails_closed(self, reap, claim, settle, execute):
        claim.return_value = [(EVENT, "untrusted", {}, 2)]
        self.assertEqual(dispatch_once(**self.args), [(EVENT, "retry")])
        execute.assert_not_called()
        self.assertFalse(settle.call_args.kwargs["delivered"])
        self.assertEqual(settle.call_args.kwargs["retry_seconds"], 60)
    @patch("app.hitl_dispatcher.execute_local_once", side_effect=RuntimeError("crash"))
    @patch("app.hitl_dispatcher.settle", side_effect=PermissionError("stale"))
    @patch("app.hitl_dispatcher.claim")
    @patch("app.hitl_dispatcher.reap_exhausted")
    def test_stale_lease_not_overwritten(self, reap, claim, settle, execute):
        claim.return_value = [(EVENT, "hitl.approval.consumed",
                               {"action_hash": "a"*64}, 3)]
        self.assertEqual(dispatch_once(**self.args), [(EVENT, "stale-lease")])
    def test_rejects_untrusted_callbacks(self):
        with self.assertRaises(TypeError):
            dispatch_once(**dict(self.args, apply_local=None))

if __name__ == "__main__":
    unittest.main()
