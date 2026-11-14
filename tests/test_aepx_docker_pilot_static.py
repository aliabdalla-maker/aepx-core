"""Static guardrails for opt-in Docker offline pilot launcher.

Does not run Docker or execute repository tests.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LAUNCHER=(ROOT/"scripts/run_aepx_offline_docker.sh").read_text(encoding="utf-8")
DOCKERFILE=(ROOT/"docker/offline-pilot/Dockerfile").read_text(encoding="utf-8")

class DockerPilotStaticTests(unittest.TestCase):
    def test_runtime_isolation_flags(self):
        for flag in ("--network none","--read-only","--cap-drop ALL",
                     "--security-opt no-new-privileges","--pids-limit 128",
                     "--memory 512m","--cpus 1","--user 10001:10001",
                     "--tmpfs /tmp:","readonly"):
            with self.subTest(flag=flag):
                self.assertIn(flag,LAUNCHER)

    def test_explicit_execution_and_no_secret_mounts(self):
        self.assertIn('"--execute"',LAUNCHER)
        self.assertIn("checkpoint_dir",LAUNCHER)
        self.assertNotIn("/var/run/docker.sock",LAUNCHER)
        self.assertNotIn("--privileged",LAUNCHER)
        self.assertNotIn("--env-file",LAUNCHER)
        self.assertNotIn("--network host",LAUNCHER)

    def test_nonroot_image(self):
        self.assertIn("USER 10001:10001",DOCKERFILE)
        self.assertIn("ENTRYPOINT",DOCKERFILE)

if __name__=="__main__":
    unittest.main()
