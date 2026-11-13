"""Offline tests for atomic remote intent state transitions."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_intent_state import IntentState, IntentTransitionDenied
from app.mcp_remote_intent_transition import transition_intent, TransitionDenied

class Cursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.args = None
    def execute(self, query, args):
        self.query, self.args = query, args
    def fetchone(self):
        return self.row

class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.request = str(uuid4()), str(uuid4())
    def call(self, cursor, **kw):
        return transition_intent(cursor, tenant_id=self.tenant,
            request_id=self.request, current=IntentState.RESERVED,
            target=IntentState.DISPATCHED, **kw)
    def test_atomic_reserved_to_dispatched(self):
        cursor = Cursor((self.request,))
        self.assertEqual(self.call(cursor), IntentState.DISPATCHED)
        self.assertIn("AND state = %s", cursor.query)
        self.assertIn("tenant_id = %s", cursor.query)
        self.assertEqual(cursor.args, ("dispatched", self.tenant, self.request, "reserved"))
    def test_stale_or_invisible_rejected(self):
        with self.assertRaises(TransitionDenied):
            self.call(Cursor(None))
        with self.assertRaises(TransitionDenied):
            self.call(Cursor((str(uuid4()),)))
    def test_uncertain_cannot_be_dispatched_again(self):
        with self.assertRaises(IntentTransitionDenied):
            transition_intent(Cursor(None), tenant_id=self.tenant,
                request_id=self.request, current=IntentState.UNCERTAIN,
                target=IntentState.DISPATCHED)
    def test_terminal_needs_evidence(self):
        with self.assertRaises(IntentTransitionDenied):
            transition_intent(Cursor(None), tenant_id=self.tenant,
                request_id=self.request, current=IntentState.DISPATCHED,
                target=IntentState.SUCCEEDED)
    def test_invalid_identity_rejected(self):
        with self.assertRaises(TransitionDenied):
            transition_intent(Cursor(None), tenant_id="bad", request_id=self.request,
                current=IntentState.RESERVED, target=IntentState.DISPATCHED)

if __name__ == "__main__":
    unittest.main()
