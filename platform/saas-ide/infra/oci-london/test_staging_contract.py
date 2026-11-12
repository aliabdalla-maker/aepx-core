"""Offline security regression tests for OCI London staging topology."""
import unittest
from pathlib import Path

ROOT = Path(__file__).parent

class StagingContractTests(unittest.TestCase):
    def test_no_public_ports_or_host_network(self):
        compose = (ROOT / "compose.staging.yml").read_text()
        self.assertNotIn("\n    ports:", compose)
        self.assertNotIn("network_mode: host", compose)
        self.assertIn("internal: true", compose)

    def test_external_execution_disabled(self):
        compose = (ROOT / "compose.staging.yml").read_text()
        self.assertIn('IDE_EXTERNAL_EXECUTION_ENABLED: "false"', compose)
        self.assertIn('IDE_MCP_EXECUTION_ENABLED: "false"', compose)

    def test_compute_opt_in_and_private(self):
        compute = (ROOT / "staging-compute.tf").read_text()
        self.assertIn("default = false", compute)
        self.assertIn("assign_public_ip = false", compute)

    def test_no_embedded_secrets(self):
        compose = (ROOT / "compose.staging.yml").read_text()
        self.assertNotIn("POSTGRES_PASSWORD:", compose)
        self.assertIn("POSTGRES_PASSWORD_FILE:", compose)

if __name__ == "__main__":
    unittest.main()
