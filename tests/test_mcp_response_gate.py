"""Offline MCP response correlation and adversarial tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_response_gate import validate_mcp_json_response
from app.mcp_contract_gate import MCPContractDenied

class TestMCPResponseGate(unittest.TestCase):
    def call(self, body, request_id=42):
        return validate_mcp_json_response(response_body=body, expected_request_id=request_id)

    def test_success_and_tool_error(self):
        body = json.dumps({"jsonrpc":"2.0","id":42,"result":{"content":[]}})
        self.assertTrue(self.call(body)["ok"])
        body = json.dumps({"jsonrpc":"2.0","id":42,"result":{"content":[],"isError":True}})
        self.assertFalse(self.call(body)["ok"])
        self.assertTrue(self.call(body)["tool_error"])

    def test_protocol_error_is_not_success(self):
        body = json.dumps({"jsonrpc":"2.0","id":42,"error":{"code":-32601,"message":"not found"}})
        self.assertEqual(self.call(body), {"ok":False,"error_code":-32601})

    def test_rejects_ambiguous_or_malformed(self):
        valid = {"jsonrpc":"2.0","id":42,"result":{"content":[]}}
        invalid = [
            {**valid,"id":43}, {**valid,"id":"42"},
            {**valid,"error":{"code":-1,"message":"fail"}},
            {**valid,"result":[]}, {**valid,"result":{}},
            {**valid,"result":{"content":[],"isError":"false"}},
            {"jsonrpc":"2.0","id":42},
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(MCPContractDenied):
                self.call(json.dumps(item))
        for raw in ('{"jsonrpc":"2.0","id":42,"id":42,"result":{"content":[]}}',
                    '{"jsonrpc":"2.0","id":42,"result":{"content":[],"x":NaN}}',
                    "x"*262145, b"\xff"):
            with self.subTest(raw=str(raw)[:30]), self.assertRaises(MCPContractDenied):
                self.call(raw)
