"""MCP POST request gate regressions, offline."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_post_request_gate import validate_mcp_post_request
from app.mcp_contract_gate import MCPContractDenied

URL="https://mcp.example.test/mcp"
HEADERS={"Content-Type":"application/json",
         "Accept":"application/json, text/event-stream"}
BODY=json.dumps({"jsonrpc":"2.0","id":9,"method":"tools/call","params":{}})
class TestPostRequestGate(unittest.TestCase):
    def call(self,**changes):
        args=dict(endpoint=URL,approved_endpoints={URL},method="POST",
                  headers=HEADERS,body=BODY,expected_request_id=9)
        args.update(changes)
        return validate_mcp_post_request(**args)
    def test_valid(self):
        self.assertEqual(self.call()["method"],"tools/call")
    def test_denied(self):
        cases=[
            {"method":"GET"},{"headers":{"Content-Type":"application/json"}},
            {"headers":{**HEADERS,"Mcp-Session-Id":"legacy"}},
            {"headers":{**HEADERS,"Last-Event-ID":"1"}},
            {"headers":{**HEADERS,"accept":"application/json"}},
            {"body":'{"jsonrpc":"2.0","id":9,"id":9,"method":"tools/call"}'},
            {"body":'{"jsonrpc":"2.0","id":9,"result":{}}'},
            {"body":'{"jsonrpc":"2.0","id":9,"method":"tools/call","params":NaN}'},
            {"body":BODY,"expected_request_id":8},
            {"body":BODY*100000},
        ]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(MCPContractDenied):
                self.call(**case)

    def test_negotiated_protocol_version_is_pinned(self):
        headers={**HEADERS,"MCP-Protocol-Version":"2025-11-25"}
        self.assertEqual(self.call(
            headers=headers,negotiated_protocol_version="2025-11-25")["request_id"],9)
        for candidate in (HEADERS,{**HEADERS,"MCP-Protocol-Version":"2025-03-26"},
                          {**HEADERS,"MCP-Protocol-Version":"2025-11-25",
                           "mcp-protocol-version":"2025-11-25"}):
            with self.subTest(headers=candidate),self.assertRaises(MCPContractDenied):
                self.call(headers=candidate,negotiated_protocol_version="2025-11-25")
