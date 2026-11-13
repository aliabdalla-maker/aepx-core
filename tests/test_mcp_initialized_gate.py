"""Offline initialized notification contract regression tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_initialized_gate import validate_mcp_initialized_notification
from app.mcp_contract_gate import MCPContractDenied

GOOD={"jsonrpc":"2.0","method":"notifications/initialized"}
class TestInitializedGate(unittest.TestCase):
    def call(self,body,version="2025-11-25"):
        return validate_mcp_initialized_notification(
            body=body,initialized_version=version,expected_version="2025-11-25")
    def test_valid(self):
        self.assertEqual(self.call(json.dumps(GOOD))["method"],
                         "notifications/initialized")
        self.assertEqual(self.call(json.dumps({**GOOD,"params":{}}))["version"],
                         "2025-11-25")
    def test_denies_wrong_notification(self):
        cases=[
            {**GOOD,"id":1},{**GOOD,"result":{}},{**GOOD,"error":{}},
            {**GOOD,"method":"tools/call"},{**GOOD,"params":{"unsafe":True}},
            {**GOOD,"extra":True},
        ]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(MCPContractDenied):
                self.call(json.dumps(case))
        for raw in ('{"jsonrpc":"2.0","method":"notifications/initialized","method":"notifications/initialized"}',
                    json.dumps(GOOD)*1000):
            with self.assertRaises(MCPContractDenied):
                self.call(raw)
        with self.assertRaises(MCPContractDenied):
            self.call(json.dumps(GOOD),version="2025-03-26")
