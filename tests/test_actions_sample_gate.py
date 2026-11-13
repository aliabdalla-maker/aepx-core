"""Tests for the fail-closed Actions evidence gate."""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "actions-sample-gate.py"
spec = importlib.util.spec_from_file_location("actions_sample_gate", path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ActionsSampleGateTests(unittest.TestCase):
    def test_failure_blocks(self):
        self.assertTrue(gate.evaluate({"sample_size": 2, "conclusion_counts":
                                      {"success": 1, "failure": 1}}))

    def test_queued_blocks(self):
        self.assertTrue(gate.evaluate({"sample_size": 1, "conclusion_counts":
                                      {"not_completed": 1}}))

    def test_missing_or_empty_evidence_blocks(self):
        self.assertTrue(gate.evaluate({}))
        self.assertTrue(gate.evaluate({"sample_size": 0, "conclusion_counts": {}}))

    def test_inconsistent_counts_block(self):
        self.assertTrue(gate.evaluate({"sample_size": 2, "conclusion_counts":
                                      {"success": 1}}))

    def test_unknown_conclusion_blocks(self):
        report = {"sample_size": 2, "status_counts": {"completed": 2},
                  "conclusion_counts": {"success": 1, "action_required": 1}}
        self.assertTrue(gate.evaluate(report))

    def test_queued_status_blocks_even_if_conclusions_claim_success(self):
        report = {"sample_size": 1, "status_counts": {"queued": 1},
                  "conclusion_counts": {"success": 1}}
        self.assertTrue(gate.evaluate(report))

    def test_missing_status_counts_blocks(self):
        self.assertTrue(gate.evaluate({"sample_size": 1,
                                       "conclusion_counts": {"success": 1}}))

    def test_successful_sample_only_passes_sample_health(self):
        self.assertEqual(gate.evaluate({"sample_size": 3, "status_counts": {"completed": 3},
                                       "conclusion_counts": {"success": 3}}), [])


if __name__ == "__main__":
    unittest.main()
