"""Offline-only supervisor plan contract tests. No Docker commands executed."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_offline_supervisor_plan import offline_supervisor_plan
from app.hitl_offline_container_policy import SandboxPolicyDenied

IMAGE = "example.local/hitl@sha256:" + "a" * 64
ID = "a" * 32

class TestOfflineSupervisorPlan(unittest.TestCase):
    def test_bounded_plan_and_cleanup(self):
        plan = offline_supervisor_plan(execution_id=ID, image_digest=IMAGE, command=("true",))
        self.assertEqual(plan["run_argv"][:4], ("docker", "run", "--name", plan["name"]))
        self.assertIn("--network=none", plan["run_argv"])
        self.assertNotIn("--rm", plan["run_argv"])
        self.assertTrue(plan["requires_identity_verification"])
        self.assertTrue(plan["requires_post_cleanup_absence_check"])
        self.assertEqual(plan["kill_argv"], ("docker", "kill", plan["name"]))
        self.assertEqual(plan["cleanup_argv"], ("docker", "rm", "--force", plan["name"]))
        self.assertTrue(plan["requires_cleanup_verification"])

    def test_rejects_invalid_identity_and_deadline(self):
        for execution_id in ("", "test", "../escape", "A" * 32):
            with self.subTest(execution_id=execution_id), self.assertRaises(SandboxPolicyDenied):
                offline_supervisor_plan(execution_id=execution_id, image_digest=IMAGE, command=("true",))
        for seconds in (0, -1, 61, float("nan"), float("inf"), True):
            with self.subTest(seconds=seconds), self.assertRaises(SandboxPolicyDenied):
                offline_supervisor_plan(execution_id=ID, image_digest=IMAGE, command=("true",), timeout_seconds=seconds)

    def test_rejects_nonfinite_cpu(self):
        for cpu in (math.nan, math.inf, -math.inf):
            with self.subTest(cpu=cpu), self.assertRaises(SandboxPolicyDenied):
                offline_supervisor_plan(execution_id=ID, image_digest=IMAGE, command=("true",), cpus=cpu)
