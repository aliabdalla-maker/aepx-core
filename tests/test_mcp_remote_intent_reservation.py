"""Offline unit tests for the SQL reservation contract."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_intent_reservation import IntentReservation, ReservationDenied, reserve_intent

class FakeCursor:
    def __init__(self, inserted=None, existing=()):
        self.inserted, self.existing, self.statements = inserted, existing, []
    def execute(self, statement, values):
        self.statements.append((statement, values))
    def fetchone(self):
        return self.inserted
    def fetchall(self):
        return self.existing

class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.intent = IntentReservation(
            str(uuid4()), str(uuid4()), str(uuid4()), "a"*64,
            "resource", "tool.read", "2025-11-25", "request-000001")

    def test_created(self):
        cursor = FakeCursor(inserted=("row",))
        self.assertEqual(reserve_intent(cursor, self.intent), "created")
        self.assertIn("ON CONFLICT DO NOTHING", cursor.statements[0][0])
        self.assertEqual(len(cursor.statements), 1)

    def test_exact_replay(self):
        cursor = FakeCursor(existing=[tuple(vars(self.intent).values()) + ("reserved",)])
        self.assertEqual(reserve_intent(cursor, self.intent), "existing")
        self.assertIn("FOR UPDATE", cursor.statements[1][0])

    def test_conflicting_key_rejected(self):
        different = tuple(vars(replace(self.intent, tool_name="tool.delete")).values()) + ("reserved",)
        with self.assertRaises(ReservationDenied):
            reserve_intent(FakeCursor(existing=[different]), self.intent)

    def test_cross_tenant_invisible_rejected(self):
        with self.assertRaises(ReservationDenied):
            reserve_intent(FakeCursor(existing=[]), self.intent)

    def test_invalid_uuid_rejected_before_sql(self):
        cursor = FakeCursor()
        with self.assertRaises(ReservationDenied):
            reserve_intent(cursor, replace(self.intent, tenant_id="not-a-uuid"))
        self.assertFalse(cursor.statements)

if __name__ == "__main__":
    unittest.main()
