"""Adversarial tests for offline 100-cycle report verification."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("cycle_verifier", pathlib.Path(__file__).resolve().parents[1] / "tools" / "verify_acceptance_cycle_report.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class CycleReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / "report.json"
        self.report = {
            "source_commit": "a" * 40, "workflow_run_id": "123",
            "requested": 2, "executed": 2, "all_passed": True,
            "independent_acceptance_established": False,
            "production_deployment_authorized": False,
            "runs": [
                {"iteration": i, "passed": True, "tests_executed": 42,
                 "return_code": 0, "elapsed_seconds": 0.1}
                for i in (1, 2)
            ],
        }

    def check(self):
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        return mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_valid_report(self):
        self.assertEqual(self.check()["executed"], 2)

    def test_rejects_wrong_provenance(self):
        self.report["source_commit"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.check()

    def test_rejects_boolean_cycle_count(self):
        self.report["executed"] = True
        with self.assertRaisesRegex(ValueError, "cycle count"):
            self.check()

    def test_rejects_duplicate_cycle_number(self):
        self.report["runs"][1]["iteration"] = 1
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_insufficient_tests(self):
        self.report["runs"][0]["tests_executed"] = 41
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()
