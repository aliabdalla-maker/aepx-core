"""Offline MCP session ordering regression tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_session_gate import (
    SessionState, accept_initialize, accept_initialized, require_authenticated_transport
)
from app.mcp_contract_gate import MCPContractDenied

class SessionGateTests(unittest.TestCase):
    def ready(self):
        state = accept_initialize(
            SessionState(), negotiated_version="2025-11-25",
            expected_version="2025-11-25", server_name="approved",
            approved_server_name="approved")
        return accept_initialized(
            state, body=json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}),
            expected_version="2025-11-25")

    def test_ordered_offline_contract(self):
        self.assertEqual(self.ready().phase, "offline_contract_complete")

    def test_notification_before_initialize_denied(self):
        with self.assertRaises(MCPContractDenied):
            accept_initialized(SessionState(), body="{}", expected_version="2025-11-25")

    def test_mismatched_server_denied(self):
        with self.assertRaises(MCPContractDenied):
            accept_initialize(SessionState(), negotiated_version="2025-11-25",
                              expected_version="2025-11-25", server_name="unknown",
                              approved_server_name="approved")

    def test_duplicate_initialize_denied(self):
        with self.assertRaises(MCPContractDenied):
            accept_initialize(self.ready(), negotiated_version="2025-11-25",
                              expected_version="2025-11-25", server_name="approved",
                              approved_server_name="approved")

    def test_gateway_assertions_required(self):
        state = self.ready()
        for kwargs in ({}, {"tls_identity_verified":True},
                       {"tls_identity_verified":True,"token_audience_verified":True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(MCPContractDenied):
                require_authenticated_transport(state, **kwargs)
        self.assertEqual(require_authenticated_transport(
            state, tls_identity_verified=True, token_audience_verified=True,
            resource_authorized=True).phase, "gateway_assertions_supplied")

if __name__ == "__main__":
    unittest.main()
