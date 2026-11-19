"""Offline endpoint policy tests. No sockets or DNS."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_endpoint_policy import validate_mcp_endpoint
from app.mcp_contract_gate import MCPContractDenied

class TestEndpointPolicy(unittest.TestCase):
    def test_exact_approved_https(self):
        endpoint="https://mcp.example.test/mcp"
        self.assertEqual(validate_mcp_endpoint(
            endpoint=endpoint,approved_endpoints={endpoint}),endpoint)
    def test_fail_closed(self):
        urls=[
            "http://mcp.example.test/mcp",
            "https://127.0.0.1/mcp",
            "https://[::1]/mcp",
            "https://localhost/mcp",
            "https://mcp.example.test:8443/mcp",
            "https://user:pass@mcp.example.test/mcp",
            "https://mcp.example.test/mcp?token=abc",
            "https://mcp.example.test/mcp#fragment",
            "https://mcp.example.test./mcp",
            "https://MCP.example.test/mcp",
            "https://mcp.example.test/%2e%2e/mcp",
            "https://mcp.example.test/\\\\mcp",
            "https://mcp.example.test/mcp\n",
        ]
        urls.extend([
            "https://mcp.example.test/a/../mcp",
            "https://mcp.example.test/a/./mcp",
            "https://mcp.example.test//mcp",
        ])
        for url in urls:
            with self.subTest(url=url),self.assertRaises(MCPContractDenied):
                validate_mcp_endpoint(endpoint=url,approved_endpoints={url})
        with self.assertRaises(MCPContractDenied):
            validate_mcp_endpoint(endpoint="https://mcp.example.test/mcp",
                                  approved_endpoints={"https://other.example.test/mcp"})
