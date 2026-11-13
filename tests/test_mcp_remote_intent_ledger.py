import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_intent_state import IntentState, IntentTransitionDenied, validate_transition
from app.mcp_remote_intent_schema import DDL

class IntentLedgerTests(unittest.TestCase):
    def test_happy_path(self):
        self.assertEqual(validate_transition(IntentState.RESERVED, IntentState.DISPATCHED), IntentState.DISPATCHED)
        self.assertEqual(validate_transition(IntentState.DISPATCHED, IntentState.SUCCEEDED, provider_evidence=True), IntentState.SUCCEEDED)

    def test_unknown_result_must_reconcile(self):
        self.assertEqual(validate_transition(IntentState.DISPATCHED, IntentState.UNCERTAIN), IntentState.UNCERTAIN)
        with self.assertRaises(IntentTransitionDenied):
            validate_transition(IntentState.UNCERTAIN, IntentState.DISPATCHED)

    def test_terminal_outcome_needs_evidence(self):
        for state in (IntentState.DISPATCHED, IntentState.UNCERTAIN):
            for target in (IntentState.SUCCEEDED, IntentState.FAILED):
                with self.subTest(state=state, target=target), self.assertRaises(IntentTransitionDenied):
                    validate_transition(state, target)

    def test_terminal_state_cannot_reopen(self):
        with self.assertRaises(IntentTransitionDenied):
            validate_transition(IntentState.SUCCEEDED, IntentState.DISPATCHED)

    def test_schema_requires_rls_and_dedupe(self):
        for required in ("FORCE ROW LEVEL SECURITY", "UNIQUE (tenant_id, idempotency_key)",
                         "UNIQUE (tenant_id, approval_id, action_hash)", "app.tenant_id",\n                         "resource_id ~", "tool_name ~", "protocol_version ~", "idempotency_key ~"):
            self.assertIn(required, DDL)

if __name__ == "__main__":
    unittest.main()
