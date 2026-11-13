"""Offline response safety contract tests; never perform network I/O."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_http_response_guard import (
    MCPResponsePolicy, MCPResponseDenied, validate_mcp_response,
    enforce_mcp_response_chunk,
)

class ResponseGuardTests(unittest.TestCase):
    def setUp(self):
        self.policy = MCPResponsePolicy(max_response_bytes=16)

    def test_json_and_sse_success(self):
        for media in ("application/json", "text/event-stream; charset=utf-8"):
            self.assertEqual(
                validate_mcp_response(200, {"Content-Type": media, "Content-Length": "12"},
                                      policy=self.policy),
                media.split(";", 1)[0],
            )

    def test_redirect_and_error_fail_closed(self):
        for status in (201, 301, 302, 303, 307, 308, 400, 401, 500, True):
            with self.subTest(status=status), self.assertRaises(MCPResponseDenied):
                validate_mcp_response(status, {"Content-Type": "application/json"},
                                      policy=self.policy)

    def test_malformed_headers_rejected(self):
        cases = (
            {"Content-Type": "text/html"},
            {"Content-Type": "application/json", "Content-Length": "17"},
            {"Content-Type": "application/json", "Content-Length": "-1"},
            {"Content-Type": "application/json", "Content-Length": "abc"},
            {"Content-Type": "application/json", "Content-Encoding": "gzip"},
            {"Content-Type": "application/json", "content-type": "application/json"},
            {"Content-Type": "application/json" + chr(10)},
            {"Content-Type": "application/json", "Location": "https://evil.test/" + chr(13)},
        )
        for headers in cases:
            with self.subTest(headers=headers), self.assertRaises(MCPResponseDenied):
                validate_mcp_response(200, headers, policy=self.policy)

    def test_streaming_byte_limit(self):
        total = enforce_mcp_response_chunk(0, b"12345678", policy=self.policy)
        self.assertEqual(enforce_mcp_response_chunk(total, b"12345678",
                         policy=self.policy), 16)
        with self.assertRaises(MCPResponseDenied):
            enforce_mcp_response_chunk(16, b"x", policy=self.policy)

    def test_invalid_budget_and_chunk_fail_closed(self):
        for policy in (MCPResponsePolicy(0), MCPResponsePolicy(True), None):
            with self.subTest(policy=policy), self.assertRaises(MCPResponseDenied):
                enforce_mcp_response_chunk(0, b"x", policy=policy)
        for total, chunk in ((-1, b"x"), (True, b"x"), (0, "x")):
            with self.assertRaises(MCPResponseDenied):
                enforce_mcp_response_chunk(total, chunk, policy=self.policy)

if __name__ == "__main__":
    unittest.main()
