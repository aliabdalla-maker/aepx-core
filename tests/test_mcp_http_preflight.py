"""Offline-only HTTPS preflight tests; no external requests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_http_preflight import validate_mcp_https_endpoint, MCPPreflightDenied

HOSTS = frozenset({"mcp.example.com"})
TOKEN = "Bearer offline-test-token"

class PreflightTests(unittest.TestCase):
    def check(self, url="https://mcp.example.com/mcp", **kw):
        params = dict(allowed_hosts=HOSTS, authorization=TOKEN)
        params.update(kw)
        return validate_mcp_https_endpoint(url, **params)

    def test_valid_allowlisted_endpoint(self):
        value = self.check()
        self.assertEqual(value.hostname, "mcp.example.com")
        self.assertEqual(value.port, 443)
        self.assertEqual(value.max_response_bytes, 1048576)

    def test_rejects_untrusted_destinations(self):
        for url in ("http://mcp.example.com/mcp", "https://localhost/mcp",
                    "https://127.0.0.1/mcp", "https://169.254.169.254/mcp",
                    "https://mcp.example.com.evil.test/mcp",
                    "https://evil.test/mcp", "https://mcp.example.com:8443/mcp",
                    "https://user:pass@mcp.example.com/mcp",
                    "https://mcp.example.com/mcp?token=abc",
                    "https://mcp.example.com/mcp#fragment",
                    "https://mcp.example.com./mcp",
                    "https://mcp.example.com%2eevil.test/mcp",
                    "https://mcp.example.com\\@evil.test/mcp",
                    "https://mcp.example.com/mcp" + chr(10)):
            with self.subTest(url=url), self.assertRaises(MCPPreflightDenied):
                self.check(url)

    def test_rejects_missing_or_invalid_authentication(self):
        for value in (None, "", "Basic abc", "Bearer ", "Bearer abc" + chr(13) + chr(10) + "X:evil", 1):
            with self.subTest(value=value), self.assertRaises(MCPPreflightDenied):
                self.check(authorization=value)

    def test_rejects_unbounded_limits(self):
        for kw in (dict(timeout_seconds=0), dict(timeout_seconds=31),
                   dict(timeout_seconds=True), dict(max_response_bytes=0),
                   dict(max_response_bytes=4194305),
                   dict(max_response_bytes=True), dict(allowed_hosts=())):
            with self.subTest(kw=kw), self.assertRaises(MCPPreflightDenied):
                self.check(**kw)

if __name__ == "__main__":
    unittest.main()
