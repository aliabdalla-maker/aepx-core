"""Offline adversarial MCP discovery policy tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_discovery_policy import authorize_discovered_tool
from app.mcp_contract_gate import MCPContractDenied

class TestMCPDiscoveryPolicy(unittest.TestCase):
    def fixture(self):
        return dict(server_id="crm-prod", tool_name="crm.update",
                    discovered_tools=[{"name": "crm.update"}, {"name": "crm.read"}],
                    trusted_server_allowlist={"crm-prod"},
                    trusted_tool_allowlist={"crm-prod": {"crm.update"}})

    def test_exact_discovered_tool(self):
        self.assertEqual(authorize_discovered_tool(**self.fixture()),
                         {"server_id": "crm-prod", "tool_name": "crm.update"})

    def test_rejects_unknown_servers_and_tools(self):
        for key, value in (("server_id", "evil"), ("tool_name", "crm.delete"),
                           ("trusted_server_allowlist", set()),
                           ("trusted_tool_allowlist", {}),
                           ("discovered_tools", [{"name": "crm.read"}]),
                           ("discovered_tools", [{"name": "crm.update"}, {"name": "crm.update"}]),
                           ("discovered_tools", [{"name": "bad/tool"}]),
                           ("discovered_tools", [{"name": "crm.update"}] * 129),
                           ("discovered_tools", None)):
            data = self.fixture()
            data[key] = value
            with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(MCPContractDenied):
                authorize_discovered_tool(**data)
