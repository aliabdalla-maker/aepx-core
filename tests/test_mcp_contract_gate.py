"""Offline MCP contract-gate regression tests: no provider or network calls."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_contract_gate import canonical_tool_call, MCPContractDenied

def digest(args):
    return hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()

class TestMCPContractGate(unittest.TestCase):
    def call(self, **changes):
        args = {"customer": "123", "amount": 5}
        params = dict(tool_name="crm.update", arguments=args,
                      allowed_tools={"crm.update"}, approved_tool="crm.update",
                      approved_arguments_sha256=digest(args), idempotency_key="run-123")
        params.update(changes)
        return canonical_tool_call(**params)

    def test_exact_approval(self):
        self.assertEqual(self.call()["tool_name"], "crm.update")
        self.assertEqual(self.call(arguments={"amount": 5, "customer": "123"})["arguments_sha256"],
                         digest({"customer": "123", "amount": 5}))

    def test_denies_unapproved_tool_and_payload(self):
        for change in ({"tool_name": "shell.exec"}, {"approved_tool": "crm.delete"},
                       {"allowed_tools": set()}, {"arguments": {"amount": 500}},
                       {"approved_arguments_sha256": "0" * 64},
                       {"idempotency_key": ""}, {"idempotency_key": "key\nunsafe"},
                       {"arguments": {"amount": float("nan")}},
                       {"arguments": {"big": "x" * 70000}}):
            with self.subTest(change=change), self.assertRaises(MCPContractDenied):
                self.call(**change)

    def test_rejects_unsupported_nested_types(self):
        with self.assertRaises(MCPContractDenied):
            self.call(arguments={"bad": object()})
