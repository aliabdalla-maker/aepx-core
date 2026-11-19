"""Offline protocol negotiation policy tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_version_policy import select_mcp_protocol_version
from app.mcp_contract_gate import MCPContractDenied

class TestVersionPolicy(unittest.TestCase):
    def test_supported_restricted_profile(self):
        result=select_mcp_protocol_version(
            server_version="2025-11-25",client_versions=["2025-11-25"])
        self.assertEqual(result["version"],"2025-11-25")
        self.assertFalse(result["supports_sessions"])
        self.assertFalse(result["supports_resume"])
    def test_reject_unsupported_and_downgrade(self):
        for version,client in (
            ("2025-03-26",["2025-11-25"]),
            ("2025-03-26",["2025-03-26","2025-11-25"]),
            ("2026-07-28",["2026-07-28"]),
            ("latest",["latest"]),
            ("2025-11-25",[])):
            with self.subTest(version=version,client=client),self.assertRaises(MCPContractDenied):
                select_mcp_protocol_version(server_version=version,
                                            client_versions=client)
