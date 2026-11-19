"""Regression checks for exact-SHA release evidence workflow coverage."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class HitlWorkflowCoverageTests(unittest.TestCase):
    def test_hitl_acceptance_runs_on_every_push(self):
        workflow=(ROOT/".github/workflows/hitl-acceptance.yml").read_text()
        head=workflow.split("permissions:",1)[0]
        self.assertIn("  push:\n",head)
        self.assertIn("  pull_request:\n",head)
        self.assertIn("  workflow_dispatch:\n",head)
        self.assertNotIn("paths:",head)
    def test_release_gate_requires_both_workflows(self):
        code=(ROOT/"scripts/verify_release_evidence.py").read_text()
        self.assertIn('REQUIRED=("CI","HITL P0 acceptance")',code)
        self.assertIn('r.get("event")=="push"',code)
if __name__=="__main__":
    unittest.main()
