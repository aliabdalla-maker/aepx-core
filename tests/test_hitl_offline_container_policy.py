"""Pure offline sandbox policy tests: Docker is never invoked."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
from app.hitl_offline_container_policy import offline_container_argv, SandboxPolicyDenied

IMAGE = "example.local/hitl-offline@sha256:" + "a" * 64

class TestOfflineSandboxPolicy(unittest.TestCase):
    def test_restricted_flags_and_no_execution(self):
        argv = offline_container_argv(image_digest=IMAGE, command=("python", "-V"))
        for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                     "--pull=never", "--security-opt=no-new-privileges=true",
                     "--init"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[-3:], [IMAGE, "python", "-V"])
        self.assertIn("--security-opt=seccomp=builtin", argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("-v", argv)
        self.assertNotIn("--volume", argv)

    def test_rejects_mutable_image(self):
        with self.assertRaises(SandboxPolicyDenied):
            offline_container_argv(image_digest="python:latest", command=("python", "-V"))

    def test_rejects_invalid_command(self):
        with self.assertRaises(SandboxPolicyDenied):
            offline_container_argv(image_digest=IMAGE, command=("python\x00unsafe",))

    def test_rejects_invalid_limits(self):
        for kwargs in ({"memory_mb": True}, {"pids_limit": 0}, {"cpus": 2},
                       {"memory_mb": 1024}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SandboxPolicyDenied):
                offline_container_argv(image_digest=IMAGE, command=("true",), **kwargs)
