"""Offline bounded SSE parser adversarial tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_sse_gate import validate_mcp_sse_response
from app.mcp_contract_gate import MCPContractDenied

BODY = json.dumps({"jsonrpc":"2.0","id":7,"result":{"content":[]}})

class TestMCPSSEGate(unittest.TestCase):
    def call(self, body):
        return validate_mcp_sse_response(response_body=body, expected_request_id=7)

    def test_single_correlated_message(self):
        self.assertTrue(self.call(": ping\n\nevent: message\ndata: " + BODY + "\n\n")["ok"])
        self.assertTrue(self.call("data: " + BODY + "\n\n")["ok"])

    def test_rejects_ambiguous_or_unsafe_streams(self):
        invalid = [
            "data: " + BODY.replace('"id": 7','"id": 8') + "\n\n",
            "event: error\ndata: " + BODY + "\n\n",
            "data: " + BODY + "\n\ndata: " + BODY + "\n\n",
            "id: 10\ndata: " + BODY + "\n\n",
            "retry: 100\ndata: " + BODY + "\n\n",
            "data: " + BODY + "\r\n\r\n",
            "data: " + BODY + "\n\ndata: " + BODY + "\n\n"*40,
            "data: " + "x"*70000 + "\n\n",
            "x-field: bad\ndata: " + BODY + "\n\n",
            ": heartbeat\n\n",
        ]
        for body in invalid:
            with self.subTest(body=body[:40]), self.assertRaises(MCPContractDenied):
                self.call(body)
