"""Offline regression tests for strict MCP response metadata policy."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_http_response_guard import (
    MCPResponseDenied, MCPResponsePolicy, validate_mcp_response,
)

class ResponsePolicyHardeningTests(unittest.TestCase):
    def test_rejects_untrusted_media_allowlist(self):
        for allowlist in (
            frozenset(), frozenset({"text/html"}), {"application/json"},
            frozenset({"application/json", "text/html"}),
        ):
            with self.subTest(allowlist=allowlist), self.assertRaises(MCPResponseDenied):
                validate_mcp_response(
                    200, {"Content-Type": "application/json"},
                    policy=MCPResponsePolicy(1024, allowlist),
                )

    def test_rejects_redirect_location_even_with_success_status(self):
        with self.assertRaises(MCPResponseDenied):
            validate_mcp_response(
                200, {"Content-Type": "application/json", "Location": "https://other.example/mcp"},
                policy=MCPResponsePolicy(1024),
            )

    def test_rejects_ambiguous_or_unsupported_media_parameters(self):
        for media in (
            "application/json; charset=latin1",
            "application/json; charset=utf-8; charset=utf-8",
            "application/json; boundary=abc",
            "text/event-stream; charset=utf-16",
        ):
            with self.subTest(media=media), self.assertRaises(MCPResponseDenied):
                validate_mcp_response(
                    200, {"Content-Type": media}, policy=MCPResponsePolicy(1024),
                )

    def test_accepts_utf8_and_unparameterized_json(self):
        for media in ("application/json", "application/json; charset=utf-8",
                      "text/event-stream; charset=utf-8"):
            with self.subTest(media=media):
                self.assertEqual(
                    validate_mcp_response(
                        200, {"Content-Type": media}, policy=MCPResponsePolicy(1024)),
                    media.split(";", 1)[0],
                )

if __name__ == "__main__":
    unittest.main()
