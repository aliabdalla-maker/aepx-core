"""Safety tests for the offline pilot executor (no subprocesses run)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("aepx_pilot",ROOT/"scripts/aepx_autonomous_pilot.py")
pilot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

class PilotTests(unittest.TestCase):
    def test_known_pattern_builds_fixed_command(self):
        command=pilot.command_for(ROOT,"test_aepx_autonomous_checkpoint.py")
        self.assertIn("-I",command)
        self.assertEqual(command[-1],"test_aepx_autonomous_checkpoint.py")
        self.assertNotIn("shell",command)

    def test_unapproved_pattern_rejected(self):
        with self.assertRaises(pilot.PilotDenied):
            pilot.command_for(ROOT,"*.py")

    def test_default_denies_execution(self):
        with self.assertRaises(pilot.PilotDenied):
            pilot.execute(ROOT,"test_aepx_autonomous_checkpoint.py")

    def test_invalid_timeout_denied_before_subprocess(self):
        for timeout in (0,121,True,1.5):
            with self.subTest(timeout=timeout),self.assertRaises(pilot.PilotDenied):
                pilot.execute(ROOT,"test_aepx_autonomous_checkpoint.py",
                              timeout=timeout,enabled=True)

    def test_symlink_target_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"tests").mkdir()
            (root/"outside.py").write_text("pass")
            (root/"tests"/"test_aepx_autonomous_checkpoint.py").symlink_to(root/"outside.py")
            with self.assertRaises(pilot.PilotDenied):
                pilot.command_for(root,"test_aepx_autonomous_checkpoint.py")

if __name__=="__main__":
    unittest.main()
