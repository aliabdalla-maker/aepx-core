"""Offline MCP session state security regressions; no network access."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_session_gate import (
    SessionState, accept_initialize, accept_initialized, require_authenticated_transport
)
from app.mcp_contract_gate import MCPContractDenied

BODY='{"jsonrpc":"2.0","method":"notifications/initialized"}'
VERSION="2025-11-25"

class TestSessionAssertions(unittest.TestCase):
    def state(self):
        initialized=accept_initialize(
            SessionState(), negotiated_version=VERSION, expected_version=VERSION,
            server_name="crm", approved_server_name="crm")
        return accept_initialized(initialized, body=BODY, expected_version=VERSION)

    def test_strict_boolean_assertions(self):
        state=self.state()
        self.assertEqual(require_authenticated_transport(
            state,tls_identity_verified=True,token_audience_verified=True,
            resource_authorized=True).phase, "gateway_assertions_supplied")
        for false_value in (1, "true", [], {}, None, False):
            with self.subTest(value=false_value), self.assertRaises(MCPContractDenied):
                require_authenticated_transport(
                    state,tls_identity_verified=false_value,
                    token_audience_verified=True,resource_authorized=True)

    def test_rejects_untrusted_state_objects(self):
        class FakeState:
            phase="offline_contract_complete"
            version=VERSION
            server_name="crm"
        with self.assertRaises(MCPContractDenied):
            require_authenticated_transport(
                FakeState(),tls_identity_verified=True,
                token_audience_verified=True,resource_authorized=True)
        with self.assertRaises(MCPContractDenied):
            accept_initialize(FakeState(),negotiated_version=VERSION,
                              expected_version=VERSION,server_name="crm",
                              approved_server_name="crm")
        with self.assertRaises(MCPContractDenied):
            accept_initialized(FakeState(),body=BODY,expected_version=VERSION)
