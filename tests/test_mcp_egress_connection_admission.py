"""Offline connection admission regression tests; no sockets or DNS requests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_http_preflight import validate_mcp_https_endpoint
from app.mcp_egress_dns_policy import validate_dns_answers, MCPEgressDenied
from app.mcp_egress_connection_admission import admit_mcp_connection

class ConnectionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.preflight = validate_mcp_https_endpoint(
            "https://mcp.example.com/mcp",
            allowed_hosts=frozenset({"mcp.example.com"}),
            authorization="Bearer offline-test-token")
        self.pin = validate_dns_answers("mcp.example.com", ["8.8.8.8"],
                                        allowed_hosts=frozenset({"mcp.example.com"}))

    def test_exact_pinned_tls_destination_accepted(self):
        admission = admit_mcp_connection(
            self.preflight, self.pin, connected_address="8.8.8.8",
            tls_server_name="mcp.example.com")
        self.assertEqual(admission.destination_ip, "8.8.8.8")
        self.assertEqual(admission.port, 443)

    def test_wrong_destination_and_tls_name_rejected(self):
        for ip, sni in (("1.1.1.1", "mcp.example.com"),
                        ("127.0.0.1", "mcp.example.com"),
                        ("8.8.8.8", "evil.example.com"),
                        ("8.8.8.8", "MCP.example.com")):
            with self.subTest(ip=ip, sni=sni), self.assertRaises(MCPEgressDenied):
                admit_mcp_connection(self.preflight, self.pin,
                                     connected_address=ip, tls_server_name=sni)

    def test_redirect_proxy_and_invalid_types_rejected(self):
        for redirect, proxy in ((1, False), (0, True), (True, False),
                                (0, 1), (-1, False)):
            with self.subTest(redirect=redirect, proxy=proxy), self.assertRaises(MCPEgressDenied):
                admit_mcp_connection(self.preflight, self.pin,
                    connected_address="8.8.8.8", tls_server_name="mcp.example.com",
                    redirect_count=redirect, proxy_enabled=proxy)

    def test_cross_hostname_dns_evidence_rejected(self):
        other = validate_dns_answers("other.example.com", ["8.8.8.8"],
                                     allowed_hosts=frozenset({"other.example.com"}))
        with self.assertRaises(MCPEgressDenied):
            admit_mcp_connection(self.preflight, other,
                connected_address="8.8.8.8", tls_server_name="mcp.example.com")

if __name__ == "__main__":
    unittest.main()
