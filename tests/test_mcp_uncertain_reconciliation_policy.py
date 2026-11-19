"""Offline regression checks for ambiguous MCP dispatch reconciliation policy.

No provider calls, network access or database required. This verifies the
state machine only; it does not authenticate external provider evidence.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_intent_state import (
    IntentState, IntentTransitionDenied, validate_transition,
)


class ReconciliationPolicyTests(unittest.TestCase):
    def test_dispatched_may_be_marked_uncertain_without_evidence(self):
        self.assertEqual(
            validate_transition(IntentState.DISPATCHED, IntentState.UNCERTAIN),
            IntentState.UNCERTAIN,
        )

    def test_uncertain_cannot_be_redispatched(self):
        for target in (IntentState.RESERVED, IntentState.DISPATCHED):
            with self.subTest(target=target):
                with self.assertRaises(IntentTransitionDenied):
                    validate_transition(IntentState.UNCERTAIN, target)

    def test_uncertain_terminal_outcomes_require_evidence(self):
        for target in (IntentState.SUCCEEDED, IntentState.FAILED):
            with self.subTest(target=target):
                for evidence in (False, None, "true", 1):
                    with self.assertRaises(IntentTransitionDenied):
                        validate_transition(
                            IntentState.UNCERTAIN, target,
                            provider_evidence=evidence,
                        )
                self.assertEqual(
                    validate_transition(
                        IntentState.UNCERTAIN, target,
                        provider_evidence=True,
                    ), target,
                )

    def test_terminal_outcomes_cannot_be_reopened(self):
        for current in (IntentState.SUCCEEDED, IntentState.FAILED):
            for target in IntentState:
                with self.subTest(current=current, target=target):
                    with self.assertRaises(IntentTransitionDenied):
                        validate_transition(current, target, provider_evidence=True)

    def test_dispatched_terminal_outcome_needs_evidence(self):
        for target in (IntentState.SUCCEEDED, IntentState.FAILED):
            with self.subTest(target=target):
                with self.assertRaises(IntentTransitionDenied):
                    validate_transition(IntentState.DISPATCHED, target)


if __name__ == "__main__":
    unittest.main()
