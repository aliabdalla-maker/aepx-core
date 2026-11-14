"""Offline unit tests for the bounded 100-cycle runner itself."""
import importlib.util
import json
import signal
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("acceptance_runner", ROOT / "tools" / "run_acceptance_100_iterations.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def invoke(self, iterations, side_effect):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "report.json"
            argv = ["runner", "--iterations", str(iterations), "--output", str(target)]
            with patch.object(sys, "argv", argv), patch.object(runner.subprocess, "run", side_effect=side_effect):
                status = runner.main()
            return status, json.loads(target.read_text())

    def test_successful_cycles_are_recorded(self):
        result = subprocess.CompletedProcess([], 0, "", "Ran 42 tests in 0.1s\n\nOK\n")
        status, report = self.invoke(3, [result, result, result])
        self.assertEqual(status, 0)
        self.assertEqual(report["executed"], 3)
        self.assertTrue(report["all_passed"])
        self.assertFalse(report["independent_acceptance_established"])

    def test_stops_on_first_failed_cycle(self):
        good = subprocess.CompletedProcess([], 0, "", "Ran 42 tests in 0.1s\n\nOK\n")
        bad = subprocess.CompletedProcess([], 1, "", "Ran 42 tests in 0.1s\n\nFAILED (failures=1)\n")
        status, report = self.invoke(100, [good, bad])
        self.assertEqual(status, 1)
        self.assertEqual(report["executed"], 2)
        self.assertFalse(report["all_passed"])

    def test_rejects_false_ok_without_test_count(self):
        forged = subprocess.CompletedProcess([], 0, "", "OK\n")
        status, report = self.invoke(1, [forged])
        self.assertEqual(status, 1)
        self.assertIsNone(report["runs"][0]["tests_executed"])

    def test_timeout_preserves_failure_report(self):
        status, report = self.invoke(100, subprocess.TimeoutExpired(["python"], 90))
        self.assertEqual(status, 1)
        self.assertEqual(report["executed"], 1)
        self.assertIn("timeout", report["runs"][0]["error"])

    def test_subprocess_launch_error_persists_report(self):
        status, report = self.invoke(100, OSError("executable unavailable"))
        self.assertEqual(status, 1)
        self.assertEqual(report["executed"], 1)
        self.assertFalse(report["runs"][0]["passed"])
        self.assertIn("OSError", report["runs"][0]["error"])

    def test_restores_handler_on_unexpected_exception(self):
        previous = signal.getsignal(signal.SIGTERM)
        with self.assertRaisesRegex(RuntimeError, "simulated crash"):
            self.invoke(1, RuntimeError("simulated crash"))
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_restores_sigterm_handler_after_success(self):
        previous = signal.getsignal(signal.SIGTERM)
        result = subprocess.CompletedProcess([], 0, "", "Ran 42 tests in 0.1s\n\nOK\n")
        status, _ = self.invoke(1, [result])
        self.assertEqual(status, 0)
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_restores_sigterm_handler_after_interrupt(self):
        previous = signal.getsignal(signal.SIGTERM)
        status, _ = self.invoke(1, KeyboardInterrupt())
        self.assertEqual(status, 130)
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_interrupt_preserves_failure_report(self):
        status, report = self.invoke(100, KeyboardInterrupt())
        self.assertEqual(status, 130)
        self.assertEqual(report["executed"], 1)
        self.assertIn("interrupted", report["runs"][0]["error"])


if __name__ == "__main__":
    unittest.main()
