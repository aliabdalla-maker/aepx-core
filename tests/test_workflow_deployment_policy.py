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

    def test_validator_rejects_missing_jobs_even_when_trigger_is_valid(self):
        self._assert_rejected(
            "deploy-oci.yml",
            "name: invalid\non:\n  workflow_dispatch:\n",
            "missing jobs mapping")

    def test_validator_rejects_missing_trigger_and_jobs(self):
        self._assert_rejected(
            "example.yml",
            "name: invalid\n",
            "missing jobs mapping")

    def test_validator_rejects_missing_protected_deployments(self):
        self._assert_rejected(
            "example.yml",
            "name: example\non:\n  workflow_dispatch:\njobs:\n  check:\n    runs-on: ubuntu-latest\n",
            "protected deployment workflow missing")


    def test_validator_rejects_duplicate_event_keys(self):
        self._assert_rejected(
            "example.yml",
            "name: ambiguous\non:\n  workflow_dispatch:\non:\n  push:\njobs:\n  check:\n    runs-on: ubuntu-latest\n",
            "duplicate mapping key: on")

    def test_validator_rejects_duplicate_job_keys(self):
        self._assert_rejected(
            "example.yml",
            "name: ambiguous\non:\n  workflow_dispatch:\njobs:\n  check:\n    runs-on: ubuntu-latest\n  check:\n    runs-on: ubuntu-latest\n",
            "duplicate mapping key: check")


    def test_validator_rejects_nested_duplicate_step_keys(self):
        self._assert_rejected(
            "example.yml",
            "name: nested\non:\n  workflow_dispatch:\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo safe\n        run: echo unsafe\n",
            "duplicate mapping key: run")

    def test_validator_rejects_invalid_yaml(self):
        self._assert_rejected(
            "example.yml",
            "name: broken\non: [workflow_dispatch\njobs:\n  check:\n    runs-on: ubuntu-latest\n",
            "invalid YAML")

    def test_validator_rejects_duplicate_nested_permissions(self):
        self._assert_rejected(
            "example.yml",
            "name: permissions\non:\n  workflow_dispatch:\npermissions:\n  contents: read\n  contents: write\njobs:\n  check:\n    runs-on: ubuntu-latest\n",
            "duplicate mapping key: contents")

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
