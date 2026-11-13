"""Offline adversarial DNS egress tests; no network operations."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_egress_dns_policy import (
    MCPEgressDenied, validate_dns_answers, verify_pinned_destination
)

ALLOW = frozenset({"mcp.example.com"})

class DNSPolicyTests(unittest.TestCase):
    def test_public_addresses_pinned(self):
        pin = validate_dns_answers("mcp.example.com", ["8.8.8.8", "1.1.1.1"], allowed_hosts=ALLOW)
        self.assertEqual(pin.addresses, ("8.8.8.8", "1.1.1.1"))
        self.assertTrue(verify_pinned_destination(pin, hostname="mcp.example.com",
                                                   connected_address="8.8.8.8"))

    def test_mixed_answers_fail_closed(self):
        for address in ("127.0.0.1", "10.0.0.1", "192.168.1.1",
                        "169.254.169.254", "172.16.0.1", "100.64.0.1",
                        "::1", "fc00::1", "fe80::1", "::ffff:8.8.8.8",
                        "0.0.0.0", "not-an-ip"):
            with self.subTest(address=address), self.assertRaises(MCPEgressDenied):
                validate_dns_answers("mcp.example.com", ["8.8.8.8", address],
                                     allowed_hosts=ALLOW)

    def test_wrong_host_and_rebinding_fail_closed(self):
        pin = validate_dns_answers("mcp.example.com", ["8.8.8.8"], allowed_hosts=ALLOW)
        for hostname, address in (("other.example.com", "8.8.8.8"),
                                  ("mcp.example.com", "1.1.1.1"),
                                  ("mcp.example.com", "127.0.0.1")):
            with self.assertRaises(MCPEgressDenied):
                verify_pinned_destination(pin, hostname=hostname,
                                          connected_address=address)

    def test_invalid_answer_sets_fail_closed(self):
        for answers in ([], ["8.8.8.8", "8.8.8.8"], ["008.008.008.008"],
                        ["8.8.8.8 "], ["8.8.8.8"] * 17, "8.8.8.8", [True]):
            with self.subTest(answers=answers), self.assertRaises(MCPEgressDenied):
                validate_dns_answers("mcp.example.com", answers, allowed_hosts=ALLOW)

    def test_hostname_allowlist_fail_closed(self):
        for hostname in ("localhost", "mcp.example.com.", "MCP.example.com",
                         "mcp..example.com", "evil.example.com"):
            with self.subTest(hostname=hostname), self.assertRaises(MCPEgressDenied):
                validate_dns_answers(hostname, ["8.8.8.8"], allowed_hosts=ALLOW)

if __name__ == "__main__":
    unittest.main()
