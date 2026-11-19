"""Offline safety checks for opt-in real-image entrypoint smoke test."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"scripts/test_aepx_docker_entrypoint_runtime.sh").read_text()

class DockerEntrypointSmokeContract(unittest.TestCase):
    def test_opt_in_and_no_implicit_image_pull(self):
        for marker in ('"--execute"', "docker image inspect", "--pull never"):
            self.assertIn(marker,SOURCE)

    def test_isolation_and_help_only(self):
        for marker in ("--network none","--read-only","--cap-drop ALL",
                       "--security-opt no-new-privileges","--user 10001:10001",
                       "--help","--checkpoint"):
            self.assertIn(marker,SOURCE)
        self.assertNotIn("--pattern test_",SOURCE)

if __name__=="__main__":
    unittest.main()
