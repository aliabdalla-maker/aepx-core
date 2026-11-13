"""Offline MCP initialize response gate regressions."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_initialize_gate import validate_mcp_initialize_response
from app.mcp_contract_gate import MCPContractDenied

RESULT={"jsonrpc":"2.0","id":11,"result":{
    "protocolVersion":"2025-11-25","capabilities":{"tools":{}},
    "serverInfo":{"name":"crm","version":"1.0"}}}
class TestInitializeGate(unittest.TestCase):
    def call(self,payload):
        return validate_mcp_initialize_response(
            response_body=payload,expected_request_id=11,
            client_versions=["2025-11-25"])
    def test_valid(self):
        self.assertEqual(self.call(json.dumps(RESULT))["server_name"],"crm")
    def test_rejects_invalid(self):
        cases=[
            {**RESULT,"id":12},
            {**RESULT,"error":{"code":-1,"message":"bad"}},
            {**RESULT,"result":{**RESULT["result"],"protocolVersion":"2025-03-26"}},
            {**RESULT,"result":{**RESULT["result"],"capabilities":[]}},
            {**RESULT,"result":{**RESULT["result"],"serverInfo":{}}},
            {**RESULT,"result":{**RESULT["result"],"serverInfo":{"name":""}}},
        ]
        for value in cases:
            with self.subTest(value=value),self.assertRaises(MCPContractDenied):
                self.call(json.dumps(value))
        for raw in ('{"jsonrpc":"2.0","id":11,"id":11,"result":{}}',
                    json.dumps(RESULT)*10000):
            with self.assertRaises(MCPContractDenied):
                self.call(raw)
