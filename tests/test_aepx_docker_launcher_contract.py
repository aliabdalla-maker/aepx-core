"""Black-box Docker launcher contract tests with a fake Docker executable.

No Docker daemon, image, network or paid resource is used.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/run_aepx_offline_docker.sh"
PATTERN = "test_aepx_autonomous_checkpoint.py"

class DockerLauncherContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.checkpoint = self.base / "checkpoint"
        self.checkpoint.mkdir()
        self.capture = self.base / "docker-args.json"
        docker = self.bin / "docker"
        docker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['AEPX_DOCKER_CAPTURE'], 'w') as f:\n"
            "    json.dump(sys.argv[1:], f)\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
                    "AEPX_DOCKER_CAPTURE": str(self.capture)}

    def run_launcher(self, *args):
        return subprocess.run(["bash", str(LAUNCHER), *args], env=self.env,
                              capture_output=True, text=True, timeout=10, check=False)

    def test_valid_invocation_has_isolation_and_mount_contract(self):
        result = self.run_launcher("--execute", str(self.checkpoint), PATTERN, "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())
        for item in ("run", "--rm", "--network", "none", "--read-only",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     "--pids-limit", "128", "--memory", "512m", "--cpus", "1",
                     "--user", "10001:10001", "--execute", "--count", "2"):
            with self.subTest(item=item):
                self.assertIn(item, args)
        self.assertIn(f"type=bind,src={ROOT.resolve()},dst=/workspace,readonly", args)
        self.assertIn(f"type=bind,src={self.checkpoint.resolve()},dst=/checkpoint", args)
        self.assertNotIn("/var/run/docker.sock", " ".join(args))

    def test_invalid_pattern_never_invokes_docker(self):
        result = self.run_launcher("--execute", str(self.checkpoint), "../../bad.py", "1")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_missing_opt_in_never_invokes_docker(self):
        result = self.run_launcher(str(self.checkpoint), PATTERN, "1")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_checkpoint_inside_repo_never_invokes_docker(self):
        result = self.run_launcher("--execute", str(ROOT), PATTERN, "1")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_symlink_checkpoint_never_invokes_docker(self):
        alias = self.base / "checkpoint-link"
        alias.symlink_to(self.checkpoint, target_is_directory=True)
        result = self.run_launcher("--execute", str(alias), PATTERN, "1")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

if __name__ == "__main__":
    unittest.main()
