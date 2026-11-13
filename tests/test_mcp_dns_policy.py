"""Offline DNS answer policy adversarial tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_dns_policy import validate_mcp_dns_answers
from app.mcp_contract_gate import MCPContractDenied

URL="https://mcp.example.test/mcp"
class TestDNSPolicy(unittest.TestCase):
    def check(self,addresses):
        return validate_mcp_dns_answers(endpoint=URL,
                                         approved_endpoints={URL},addresses=addresses)
    def test_public_answers(self):
        result=self.check(["8.8.8.8","1.1.1.1"])
        self.assertEqual(result["addresses"],("1.1.1.1","8.8.8.8"))
    def test_rejects_private_metadata_mixed_and_malformed(self):
        for addresses in (
            [],["127.0.0.1"],["10.0.0.1"],["192.168.1.1"],
            ["169.254.169.254"],["100.100.100.200"],["0.0.0.0"],
            ["::1"],["fe80::1"],["fc00::1"],["::ffff:127.0.0.1"],
            ["8.8.8.8","10.0.0.1"],["8.8.8.8","8.8.8.8"],
            ["8.8.8.8%eth0"],["not-an-ip"],["8.8.8.8"]*17):
            with self.subTest(addresses=addresses),self.assertRaises(MCPContractDenied):
                self.check(addresses)
    def test_endpoint_must_be_trusted(self):
        with self.assertRaises(MCPContractDenied):
            validate_mcp_dns_answers(endpoint=URL,
                approved_endpoints={"https://other.example.test/mcp"},
                addresses=["8.8.8.8"])
