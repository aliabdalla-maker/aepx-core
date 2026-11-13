"""Offline MCP handshake composition regression tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_handshake_policy import validate_mcp_handshake
from app.mcp_contract_gate import MCPContractDenied

INIT={"jsonrpc":"2.0","id":11,"result":{
    "protocolVersion":"2025-11-25","capabilities":{"tools":{}},
    "serverInfo":{"name":"crm","version":"1.0"}}}
ACK={"jsonrpc":"2.0","method":"notifications/initialized"}
class TestHandshakePolicy(unittest.TestCase):
    def call(self,**changes):
        args=dict(initialize_response=json.dumps(INIT),initialize_request_id=11,
                  initialized_notification=json.dumps(ACK),
                  client_versions=["2025-11-25"],approved_server_name="crm",
                  approved_protocol_version="2025-11-25")
        args.update(changes)
        return validate_mcp_handshake(**args)
    def test_valid_offline_sequence(self):
        result=self.call()
        self.assertTrue(result["offline_contract_valid"])
        self.assertEqual(result["server_name"],"crm")
    def test_fail_closed(self):
        cases=[
            {"approved_server_name":"other"},
            {"approved_server_name":""},
            {"approved_protocol_version":"2025-03-26"},
            {"approved_protocol_version":""},
            {"approved_protocol_version":None},
            {"client_versions":None},
            {"client_versions":[]},
            {"client_versions":["2025-11-25"]*33},
            {"client_versions":[20251125]},
            {"client_versions":["2025-11-25", None]},
            {"client_versions":["2025-11-25", "x"*33]},
            {"client_versions":{"2025-11-25": True}},
            {"initialize_request_id":True},
            {"initialize_request_id":"11"},
            {"initialized_notification":json.dumps({**ACK,"id":11})},
            {"initialized_notification":json.dumps({**ACK,"method":"tools/call"})},
            {"initialize_response":json.dumps({**INIT,"result":{
                **INIT["result"],"protocolVersion":"2025-03-26"}})},
        ]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(MCPContractDenied):
                self.call(**case)
