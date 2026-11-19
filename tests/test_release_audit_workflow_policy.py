"""Static safety tests for release-readiness workflow configuration."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aepx-release-readiness.yml"

class ReleaseAuditPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_concurrency_is_scoped_to_ref(self):
        group = self.doc["concurrency"]["group"]
        self.assertIn("aepx-release-audit-", group)
        self.assertIn("github.ref", group)
        self.assertEqual(self.doc["concurrency"]["cancel-in-progress"], "true")

    def test_release_audit_keeps_essential_steps(self):
        steps = self.doc["jobs"]["audit"]["steps"]
        commands = [step.get("run", "") for step in steps]
        self.assertTrue(any("scripts/aepx-release-audit.sh" in cmd for cmd in commands))
        self.assertTrue(any("docker compose -f compose.codespaces.yml down" in cmd for cmd in commands))
        self.assertTrue(any("docker network inspect aepx-dev-shared" in cmd for cmd in commands))
        self.assertTrue(any(step.get("uses", "").startswith("actions/upload-artifact@") for step in steps))

    def test_workflow_permissions_are_read_only(self):
        self.assertEqual(self.doc.get("permissions"), {"contents": "read"})

if __name__ == "__main__":
    unittest.main()
