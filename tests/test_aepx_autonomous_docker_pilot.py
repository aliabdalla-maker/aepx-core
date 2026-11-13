"""Offline Docker command policy tests; no Docker daemon required."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("docker_pilot", ROOT / "scripts/aepx_autonomous_docker_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
IMAGE = "python@sha256:" + "a" * 64

class DockerPilotTests(unittest.TestCase):
    def test_default_dry_run_has_restrictions(self):
        result = pilot.run(ROOT, "test_aepx_autonomous_checkpoint.py", IMAGE)
        self.assertEqual(result["status"], "dry-run")
        cmd = result["command"]
        for token in ("--network=none", "--read-only", "--cap-drop=ALL",
                      "--security-opt=no-new-privileges", "--pull=never",
                      "--user=65534:65534", "--pids-limit=64"):
            self.assertIn(token, cmd)
        self.assertTrue(any("readonly" in part and "type=bind" in part for part in cmd))
        self.assertNotIn("--privileged", cmd)

    def test_image_must_be_digest_pinned(self):
        for image in ("python:3.12", "python@sha256:invalid", "ubuntu@sha256:"+"a"*64):
            with self.subTest(image=image), self.assertRaises(pilot.PilotDenied):
                pilot.build_command(ROOT,"test_aepx_autonomous_checkpoint.py",image)

    def test_reject_unapproved_test(self):
        with self.assertRaises(pilot.PilotDenied):
            pilot.build_command(ROOT,"*.py",IMAGE)

    def test_reject_bad_timeout(self):
        for timeout in (0,121,True,1.5):
            with self.subTest(timeout=timeout), self.assertRaises(pilot.PilotDenied):
                pilot.build_command(ROOT,"test_aepx_autonomous_checkpoint.py",IMAGE,timeout)

    def test_symlink_test_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"tests").mkdir()
            target = root/"source.py"
            target.write_text("pass")
            (root/"tests"/"test_aepx_autonomous_checkpoint.py").symlink_to(target)
            with self.assertRaises(pilot.PilotDenied):
                pilot.build_command(root,"test_aepx_autonomous_checkpoint.py",IMAGE)

if __name__ == "__main__":
    unittest.main()
