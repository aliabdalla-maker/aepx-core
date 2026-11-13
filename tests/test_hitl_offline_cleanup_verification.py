"""Offline identity and cleanup evidence checks; no Docker execution."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_offline_cleanup_verification import (
    verify_offline_container_snapshot, verify_offline_cleanup_absent)
from app.hitl_offline_container_policy import SandboxPolicyDenied

class TestOfflineCleanupEvidence(unittest.TestCase):
    def test_identity_and_state(self):
        snapshot = {"Name": "/aepx-offline-" + "a"*32, "Id": "b"*64,
                    "Image": "sha256:"+"c"*64, "State": {"Running": False}}
        result = verify_offline_container_snapshot(
            snapshot, expected_name="aepx-offline-"+"a"*32,
            expected_image_id="sha256:"+"c"*64)
        self.assertFalse(result["running"])
        for wrong in (dict(snapshot, Name="/wrong"), dict(snapshot, Id="short"),
                      dict(snapshot, Image="sha256:"+"d"*64)):
            with self.assertRaises(SandboxPolicyDenied):
                verify_offline_container_snapshot(
                    wrong, expected_name="aepx-offline-"+"a"*32,
                    expected_image_id="sha256:"+"c"*64)

    def test_cleanup_requires_two_independent_signals(self):
        self.assertTrue(verify_offline_cleanup_absent(True, matching_processes_absent=True))
        for a,b in ((False,True),(True,False),(None,True),(True,None)):
            with self.assertRaises(SandboxPolicyDenied):
                verify_offline_cleanup_absent(a, matching_processes_absent=b)
