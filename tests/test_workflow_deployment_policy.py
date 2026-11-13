"""Regression tests for deployment trigger policy."""
import unittest
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("deploy-oci.yml", "azure-container-webapp.yml", "aws.yml", "google.yml", "alibabacloud.yml", "ibm.yml", "openshift.yml", "tencent.yml", "octopusdeploy.yml")

class DeploymentPolicyTests(unittest.TestCase):
    def test_manual_dispatch_is_only_trigger(self):
        for name in NAMES:
            with self.subTest(name=name):
                doc = yaml.load((ROOT / ".github" / "workflows" / name).read_text(), Loader=yaml.BaseLoader)
                self.assertEqual(set(doc["on"]), {"workflow_dispatch"})

    def test_validator_rejects_automatic_deployment_trigger(self):
        self._assert_rejected("deploy-oci.yml", "name: forbidden\non:\n  push:\n    branches: [master]\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n", "workflow_dispatch only")

    def test_validator_rejects_merge_conflict(self):
        self._assert_rejected("example.yml", "name: example\non:\n  workflow_dispatch:\njobs:\n  check:\n    runs-on: ubuntu-latest\n<<<<<<< HEAD\n", "unresolved merge conflict")

    def test_validator_rejects_missing_protected_deployments(self):
        self._assert_rejected(
            "example.yml",
            "name: example\non:\n  workflow_dispatch:\njobs:\n  check:\n    runs-on: ubuntu-latest\n",
            "protected deployment workflow missing")

    def _assert_rejected(self, name, content, expected):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            shutil.copy2(ROOT / "scripts" / "check_workflow_integrity.py",
                         root / "scripts" / "check_workflow_integrity.py")
            (workflows / name).write_text(content, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(root / "scripts" / "check_workflow_integrity.py")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)

if __name__ == "__main__":
    unittest.main()
