"""MCP offline composed preflight security tests."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_preflight import prepare_mcp_preflight
from app.mcp_contract_gate import MCPContractDenied

class TestMCPPreflight(unittest.TestCase):
    def fixture(self):
        digest = hashlib.sha256(b'{"x":1}').hexdigest()
        return dict(
            tenant_id="tenant-a", run_id="run-a", approval_id="approval-a",
            server_id="crm-prod", tool_name="crm.update", arguments={"x":1},
            discovered_tools=[{"name":"crm.update"}],
            trusted_server_allowlist={"crm-prod"},
            trusted_tool_allowlist={"crm-prod":{"crm.update"}},
            trusted_approval={"tenant_id":"tenant-a","run_id":"run-a",
                              "id":"approval-a","state":"consumed",
                              "tool_name":"crm.update","args_sha256":digest},
            trusted_execution={"tenant_id":"tenant-a","run_id":"run-a",
                               "approval_id":"approval-a","state":"reserved",
                               "idempotency_key":"stable-1"},
            request_id=11, client_name="aepx", client_version="1.0")

    def test_exact_trusted_preflight(self):
        result = prepare_mcp_preflight(**self.fixture())
        self.assertEqual(result["idempotency_key"], "stable-1")
        self.assertEqual(result["envelope"]["jsonrpc"]["params"]["arguments"], {"x":1})

    def test_rejects_cross_tenant_and_changed_payload(self):
        cases = [
            ("tenant_id","tenant-b"),
            ("run_id","run-b"),
            ("approval_id","approval-b"),
            ("tool_name","crm.delete"),
            ("arguments",{"x":2}),
            ("server_id","rogue"),
            ("discovered_tools",[{"name":"crm.read"}]),
            ("trusted_server_allowlist",set()),
        ]
        for key, value in cases:
            data=self.fixture()
            data[key]=value
            with self.subTest(key=key), self.assertRaises((MCPContractDenied, KeyError)):
                prepare_mcp_preflight(**data)
        for field, value in (("state","pending"),("tenant_id","tenant-b")):
            data=self.fixture()
            data["trusted_approval"]={**data["trusted_approval"],field:value}
            with self.assertRaises(MCPContractDenied):
                prepare_mcp_preflight(**data)
            data=self.fixture()
            data["trusted_execution"]={**data["trusted_execution"],field:value}
            with self.assertRaises(MCPContractDenied):
                prepare_mcp_preflight(**data)
