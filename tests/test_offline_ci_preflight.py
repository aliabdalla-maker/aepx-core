"""Contract tests for offline preflight evidence and fail-closed behavior."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "offline-ci-preflight.py"
spec = importlib.util.spec_from_file_location("offline_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OfflinePreflightEvidenceTests(unittest.TestCase):
    def test_pass_evidence_includes_commit_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            with patch.object(module.importlib.util, "find_spec", return_value=object()), \
                 patch.object(module.subprocess, "run", side_effect=self._run_success):
                self.assertEqual(module.main(["--json-output", str(output)]), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["scope"], "workflow-policy-only")
            self.assertEqual(evidence["git_commit"], "test-commit")
            self.assertTrue(evidence["overall_passed"])
            self.assertEqual(evidence["passed"], evidence["total"])

    def test_timeout_fails_closed_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            with patch.object(module.importlib.util, "find_spec", return_value=object()), \
                 patch.object(module.subprocess, "run", side_effect=self._run_timeout):
                self.assertEqual(module.main(["--timeout", "1", "--json-output", str(output)]), 1)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(evidence["overall_passed"])
            self.assertTrue(all(c["timed_out"] and c["exit_code"] == 124
                                for c in evidence["checks"]))

    def test_git_lookup_timeout_does_not_hang_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            def run(command, **kwargs):
                if command[:2] == ["git", "rev-parse"]:
                    raise subprocess.TimeoutExpired(command, 1)
                return subprocess.CompletedProcess(command, 0)
            with patch.object(module.importlib.util, "find_spec", return_value=object()), \
                 patch.object(module.subprocess, "run", side_effect=run):
                self.assertEqual(module.main(["--timeout", "1", "--json-output", str(output)]), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsNone(evidence["git_commit"])

    def test_missing_executable_fails_closed_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            def run(command, **kwargs):
                if command[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(command, 0, stdout="test-commit")
                raise FileNotFoundError("missing executable")
            with patch.object(module.importlib.util, "find_spec", return_value=object()), \
                 patch.object(module.subprocess, "run", side_effect=run):
                self.assertEqual(module.main(["--json-output", str(output)]), 1)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(evidence["overall_passed"])
            self.assertTrue(all(c["exit_code"] == 127 and not c["passed"]
                                for c in evidence["checks"]))

    @staticmethod
    def _run_success(command, **kwargs):
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, stdout="test-commit\n")
        return subprocess.CompletedProcess(command, 0)

    @staticmethod
    def _run_timeout(command, **kwargs):
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, stdout="test-commit\n")
        raise subprocess.TimeoutExpired(command, 1)


if __name__ == "__main__":
    unittest.main()
