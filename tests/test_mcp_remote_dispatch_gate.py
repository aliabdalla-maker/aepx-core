"""Remote dispatch gate regression tests; no network or side effects."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_dispatch_gate import (
    RemoteDispatchIntent, VerifiedGatewayContext,
    RemoteDispatchDenied, validate_remote_dispatch
)

class RemoteDispatchGateTests(unittest.TestCase):
    def setUp(self):
        self.intent = RemoteDispatchIntent(
            tenant_id=str(uuid4()), approval_id=str(uuid4()),
            action_hash="a" * 64, resource_id="approved-resource",
            protocol_version="2025-11-25", idempotency_key="request-000001",
            tool_name="tool.read")
        self.ctx = VerifiedGatewayContext(
            tenant_id=self.intent.tenant_id, approval_id=self.intent.approval_id,
            action_hash=self.intent.action_hash, resource_id=self.intent.resource_id,
            protocol_version=self.intent.protocol_version, tool_name=self.intent.tool_name, tls_peer_verified=True,
            audience_verified=True, resource_authorized=True, approval_verified=True)

    def test_matching_assertions(self):
        self.assertEqual(validate_remote_dispatch(self.intent, self.ctx), self.intent)

    def test_each_assertion_fail_closed(self):
        for field in ("tls_peer_verified", "audience_verified",
                      "resource_authorized", "approval_verified"):
            with self.subTest(field=field), self.assertRaises(RemoteDispatchDenied):
                validate_remote_dispatch(self.intent, replace(self.ctx, **{field: False}))

    def test_cross_tenant_and_approval_rejected(self):
        for field in ("tenant_id", "approval_id", "action_hash",
                      "resource_id", "protocol_version", "tool_name"):
            with self.subTest(field=field), self.assertRaises(RemoteDispatchDenied):
                validate_remote_dispatch(self.intent, replace(self.ctx, **{field: "mismatch"}))

    def test_invalid_idempotency_key_rejected(self):
        for key in ("", "short", "../unsafe", " " * 20):
            with self.subTest(key=key), self.assertRaises(RemoteDispatchDenied):
                validate_remote_dispatch(replace(self.intent, idempotency_key=key), self.ctx)

    def test_invalid_hash_rejected(self):
        with self.assertRaises(RemoteDispatchDenied):
            validate_remote_dispatch(replace(self.intent, action_hash="A" * 64), self.ctx)

    def test_substituted_tool_name_rejected(self):
        with self.assertRaises(RemoteDispatchDenied):
            validate_remote_dispatch(replace(self.intent,tool_name="tool.delete"),self.ctx)

    def test_invalid_identifier_shapes_rejected(self):
        cases = (
            ("resource_id", "resource\\nspoof"),
            ("resource_id", "resource with spaces"),
            ("tool_name", "tool\\x00execute"),
            ("tool_name", "tool\\nexecute"),
            ("protocol_version", "2025-11-25\\n"),
            ("protocol_version", "latest"),
            ("protocol_version", "2025-13-25"),
            ("protocol_version", "2025-02-30"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(RemoteDispatchDenied):
                validate_remote_dispatch(replace(self.intent, **{field: value}), self.ctx)

    def test_truthy_nonboolean_gateway_assertion_rejected(self):
        with self.assertRaises(RemoteDispatchDenied):
            validate_remote_dispatch(self.intent, replace(self.ctx, tls_peer_verified=1))

    def test_trusted_protocol_allowlist(self):
        self.assertEqual(validate_remote_dispatch(
            self.intent,self.ctx,require_approved_version=True,
            approved_protocol_versions=frozenset({"2025-11-25"})),self.intent)
        for versions in (None, frozenset(), frozenset({"2025-03-26"}),
                         ["2025-11-25"], frozenset({123})):
            with self.subTest(versions=versions),self.assertRaises(RemoteDispatchDenied):
                validate_remote_dispatch(
                    self.intent,self.ctx,require_approved_version=True,
                    approved_protocol_versions=versions)

if __name__ == "__main__":
    unittest.main()
