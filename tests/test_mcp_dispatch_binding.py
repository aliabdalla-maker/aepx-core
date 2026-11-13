"""Pure MCP approval binding regression tests; no DB or network."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_dispatch_binding import bind_approved_mcp_dispatch
from app.mcp_contract_gate import MCPContractDenied

ARGS = {"record": "123", "value": 5}
DIGEST = hashlib.sha256(json.dumps(ARGS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class TestMCPDispatchBinding(unittest.TestCase):
    def fixture(self):
        return dict(tenant_id="tenant-A", run_id="run-A", approval_id="approval-A",
                    tool_name="crm.update", arguments=ARGS, allowed_tools={"crm.update"},
                    trusted_approval={"tenant_id": "tenant-A", "run_id": "run-A",
                                      "id": "approval-A", "state": "consumed",
                                      "tool_name": "crm.update", "arguments_sha256": DIGEST},
                    trusted_execution={"tenant_id": "tenant-A", "run_id": "run-A",
                                       "approval_id": "approval-A", "state": "reserved",
                                       "idempotency_key": "stable-123"})

    def test_exact_bound_contract(self):
        result = bind_approved_mcp_dispatch(**self.fixture())
        self.assertEqual(result["idempotency_key"], "stable-123")
        self.assertEqual(result["arguments_sha256"], DIGEST)

    def test_cross_tenant_and_replay_denied(self):
        for key, value in (("tenant_id", "tenant-B"), ("run_id", "run-B"),
                           ("approval_id", "approval-B"), ("tool_name", "shell.exec"),
                           ("arguments", {"record": "123", "value": 500})):
            args = self.fixture()
            args[key] = value
            with self.subTest(key=key), self.assertRaises(MCPContractDenied):
                bind_approved_mcp_dispatch(**args)
        for field, changes in (("trusted_approval", {"state": "approved"}),
                               ("trusted_approval", {"tenant_id": "tenant-B"}),
                               ("trusted_execution", {"state": "dispatching"}),
                               ("trusted_execution", {"approval_id": "approval-B"}),
                               ("trusted_execution", {"idempotency_key": ""})):
            args = self.fixture()
            args[field] = {**args[field], **changes}
            with self.subTest(field=field, changes=changes), self.assertRaises(MCPContractDenied):
                bind_approved_mcp_dispatch(**args)
