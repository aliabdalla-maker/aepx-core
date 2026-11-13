"""Offline protocol-envelope regression suite; no HTTP requests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_contract_gate import canonical_tool_call, MCPContractDenied
from app.mcp_protocol_envelope import build_mcp_tool_call
import hashlib

class TestMCPEnvelope(unittest.TestCase):
    def fixture(self):
        payload = '{"x":1}'
        call = canonical_tool_call(
            tool_name="crm.update", arguments={"x": 1},
            allowed_tools={"crm.update"}, approved_tool="crm.update",
            approved_arguments_sha256=hashlib.sha256(payload.encode()).hexdigest(),
            idempotency_key="stable-123")
        return dict(bound_call=call, request_id=7, client_name="aepx",
                    client_version="1.0")

    def test_stateless_routing_and_payload(self):
        result = build_mcp_tool_call(**self.fixture())
        self.assertEqual(result["headers"]["Mcp-Method"], "tools/call")
        self.assertEqual(result["headers"]["Mcp-Name"], "crm.update")
        self.assertEqual(result["headers"]["MCP-Protocol-Version"], "2026-07-28")
        self.assertEqual(result["jsonrpc"]["params"]["arguments"], {"x": 1})
        meta = result["jsonrpc"]["params"]["_meta"]
        self.assertEqual(meta["io.modelcontextprotocol/protocolVersion"], result["headers"]["MCP-Protocol-Version"])
        self.assertEqual(meta["io.modelcontextprotocol/clientCapabilities"], {})
        self.assertEqual(result["headers"]["Content-Type"], "application/json")
        self.assertEqual(result["jsonrpc"]["params"]["_meta"]
                         ["io.modelcontextprotocol/clientInfo"]["name"], "aepx")

    def test_rejects_tampering_and_bad_headers(self):
        for key, value in (("request_id", True), ("client_name", "evil\nname"),
                           ("client_version", ""), ("bound_call", {})):
            data = self.fixture()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(MCPContractDenied):
                build_mcp_tool_call(**data)
        for change in ({"tool_name": "shell.exec"}, {"arguments_json": '{"x":2}'},
                       {"arguments_sha256": "0"*64}, {"arguments_json": '{"x": 1}'}):
            data = self.fixture()
            data["bound_call"] = {**data["bound_call"], **change}
            with self.subTest(change=change), self.assertRaises(MCPContractDenied):
                build_mcp_tool_call(**data)
