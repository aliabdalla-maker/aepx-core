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

    def test_newest_run_wins_even_if_input_reordered(self):
        sha, workflow = "a" * 40, ".github/workflows/ci.yml"
        report = {"runs": [
            {"id": 1, "created_at": "2026-11-13T10:00:00Z", "run_attempt": 1,
             "head_sha": sha, "workflow_path": workflow,
             "status": "completed", "conclusion": "success"},
            {"id": 2, "created_at": "2026-11-13T11:00:00Z", "run_attempt": 1,
             "head_sha": sha, "workflow_path": workflow,
             "status": "queued", "conclusion": None}]}
        self.assertTrue(gate.evaluate_required(report, sha, [workflow]))

    def test_required_workflows_are_sha_bound(self):
        sha = "a" * 40
        report = {"runs": [
            {"id": 1, "created_at": "2026-11-13T10:00:00Z", "run_attempt": 1, "head_sha": sha, "workflow_path": ".github/workflows/ci.yml",
             "status": "completed", "conclusion": "success"},
            {"id": 2, "created_at": "2026-11-13T11:00:00Z", "run_attempt": 1, "head_sha": "b" * 40, "workflow_path": ".github/workflows/security.yml",
             "status": "completed", "conclusion": "success"}]}
        self.assertEqual(gate.evaluate_required(report, sha, [".github/workflows/ci.yml"]), [])
        self.assertTrue(gate.evaluate_required(report, sha, [".github/workflows/security.yml"]))

    def test_required_workflow_fails_closed(self):
        sha = "a" * 40
        self.assertTrue(gate.evaluate_required({}, sha, [".github/workflows/ci.yml"]))
        self.assertTrue(gate.evaluate_required({"runs": []}, "bad", [".github/workflows/ci.yml"]))
        self.assertTrue(gate.evaluate_required({"runs": []}, sha, []))
        report = {"runs": [{"head_sha": sha, "workflow_path": ".github/workflows/ci.yml",
                            "status": "queued", "conclusion": None}]}
        self.assertTrue(gate.evaluate_required(report, sha, [".github/workflows/ci.yml"]))

    def test_latest_matching_failure_overrides_earlier_success(self):
        sha = "a" * 40
        workflow = ".github/workflows/ci.yml"
        report = {"runs": [
            {"head_sha": sha, "workflow_path": workflow,
             "status": "completed", "conclusion": "failure"},
            {"head_sha": sha, "workflow_path": workflow,
             "status": "completed", "conclusion": "success"}]}
        self.assertTrue(gate.evaluate_required(report, sha, [workflow]))

    def test_latest_matching_queued_overrides_earlier_success(self):
        sha = "a" * 40
        workflow = ".github/workflows/ci.yml"
        report = {"runs": [
            {"head_sha": sha, "workflow_path": workflow,
             "status": "queued", "conclusion": None},
            {"head_sha": sha, "workflow_path": workflow,
             "status": "completed", "conclusion": "success"}]}
        self.assertTrue(gate.evaluate_required(report, sha, [workflow]))

    def test_successful_sample_only_passes_sample_health(self):
        self.assertEqual(gate.evaluate({"sample_size": 3, "status_counts": {"completed": 3},
                                       "conclusion_counts": {"success": 3}}), [])


if __name__ == "__main__":
    unittest.main()
