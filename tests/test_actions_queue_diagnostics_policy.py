"""Static safety checks for manually invoked Actions queue diagnostics."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github" / "workflows" / "actions-queue-diagnostics.yml"

class ActionsQueueDiagnosticsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.load(PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_manual_only(self):
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})

    def test_read_only_token(self):
        self.assertEqual(self.workflow["permissions"], {"actions": "read", "contents": "read"})

    def test_bounded_diagnostic_and_timeout(self):
        job = self.workflow["jobs"]["inspect"]
        self.assertEqual(job["timeout-minutes"], "5")
        command = job["steps"][0]["run"]
        self.assertIn("per_page=100", command)
        self.assertIn("shown >= 20", command)
        self.assertIn("age_minutes", command)

    def test_no_mutating_commands(self):
        command = self.workflow["jobs"]["inspect"]["steps"][0]["run"]
        for forbidden in ("cancelWorkflowRun", "deleteWorkflowRun", "workflow_dispatches", "POST ", "DELETE "):
            self.assertNotIn(forbidden, command)

if __name__ == "__main__":
    unittest.main()
