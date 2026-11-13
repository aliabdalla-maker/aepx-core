"""Regression tests for deployment trigger policy."""
import unittest
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

if __name__ == "__main__":
    unittest.main()
