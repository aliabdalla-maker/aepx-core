"""No Docker execution: adversarial lifecycle transition tests."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_offline_supervisor_transitions import offline_supervisor_transition as step
from app.hitl_offline_container_policy import SandboxPolicyDenied

NAME = "aepx-offline-" + "a" * 32
IMAGE = "sha256:" + "c" * 64
CID = "b" * 64

def snapshot(running):
    return {"Name": "/" + NAME, "Id": CID, "Image": IMAGE,
            "State": {"Running": running},
            "HostConfig": {"NetworkMode": "none", "Privileged": False,
                           "ReadonlyRootfs": True, "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges=true", "seccomp=builtin"],
                           "PidsLimit": 32, "Memory": 134217728,
                           "MemorySwap": 134217728}}

def transition(phase, running=False, **kwargs):
    if phase == "running" and "expected_container_id" not in kwargs:
        kwargs["expected_container_id"] = CID
    return step(phase=phase, snapshot=snapshot(running),
                expected_name=NAME, expected_image_id=IMAGE, **kwargs)

class TestOfflineSupervisorTransitions(unittest.TestCase):
    def test_created_requires_stopped_identity(self):
        self.assertEqual(transition("created")["action"], "start_by_id")
        with self.assertRaises(SandboxPolicyDenied):
            transition("created", running=True)

    def test_running_poll_exit_and_deadline(self):
        self.assertEqual(transition("running", running=True,
                                   elapsed_seconds=2, timeout_seconds=10)["action"], "poll_by_id")
        killed = transition("running", running=True, elapsed_seconds=10, timeout_seconds=10)
        self.assertEqual(killed["argv"], ("docker", "kill", CID))
        self.assertEqual(transition("running", elapsed_seconds=1,
                                    timeout_seconds=10)["action"], "inspect_exit_by_id")

    def test_bad_deadline_and_hostile_snapshot(self):
        for elapsed in (None, -1, math.inf, math.nan, True):
            with self.subTest(elapsed=elapsed), self.assertRaises(SandboxPolicyDenied):
                transition("running", running=True, elapsed_seconds=elapsed, timeout_seconds=10)
        with self.assertRaises(SandboxPolicyDenied):
            step(phase="running", snapshot={**snapshot(True), "Id": "x"},
                 expected_name=NAME, expected_image_id=IMAGE,
                 elapsed_seconds=11, timeout_seconds=10)

    def test_running_rejects_container_substitution(self):
        with self.assertRaises(SandboxPolicyDenied):
            transition("running", running=True, elapsed_seconds=10,
                       timeout_seconds=10, expected_container_id="d" * 64)
        with self.assertRaises(SandboxPolicyDenied):
            step(phase="running", snapshot=snapshot(True),
                 expected_name=NAME, expected_image_id=IMAGE,
                 elapsed_seconds=10, timeout_seconds=10)

    def test_cleanup_requires_both_signals(self):
        self.assertEqual(step(phase="removed", inspect_not_found=True,
                              matching_processes_absent=True)["phase"], "clean")
        for a,b in ((False, True), (True, False), (None, True)):
            with self.assertRaises(SandboxPolicyDenied):
                step(phase="removed", inspect_not_found=a, matching_processes_absent=b)

    def test_no_implicit_destructive_actions(self):
        for phase in ("", "verified", "timed_out", "stopped", "clean"):
            with self.subTest(phase=phase), self.assertRaises(SandboxPolicyDenied):
                transition(phase)
