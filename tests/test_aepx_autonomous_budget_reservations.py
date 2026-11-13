"""Transactional budget safety tests, entirely offline."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("budget",ROOT/"scripts/aepx_autonomous_budget_reservations.py")
budget=importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"budget.sqlite"
        self.conn=budget.connect(self.path)
        budget.initialize(self.conn,"10")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_reserve_and_settle(self):
        budget.reserve(self.conn,"r1","4")
        self.assertEqual(budget.snapshot(self.conn)["held_usd"],"4")
        budget.settle(self.conn,"r1","2")
        state=budget.snapshot(self.conn)
        self.assertEqual(state["spent_usd"],"2")
        self.assertEqual(state["held_usd"],"0")

    def test_duplicate_reservation_and_settlement_denied(self):
        budget.reserve(self.conn,"r1","2")
        with self.assertRaises(sqlite3.IntegrityError):
            budget.reserve(self.conn,"r1","2")
        budget.settle(self.conn,"r1","1")
        with self.assertRaises(budget.BudgetDenied):
            budget.settle(self.conn,"r1","1")

    def test_concurrent_connections_cannot_overspend(self):
        second=budget.connect(self.path)
        try:
            budget.reserve(self.conn,"r1","6")
            with self.assertRaises(budget.BudgetDenied):
                budget.reserve(second,"r2","5")
        finally:
            second.close()

    def test_uncertain_reservation_survives_restart(self):
        budget.reserve(self.conn,"r1","8")
        budget.mark_uncertain(self.conn,"r1")
        self.conn.close()
        self.conn=budget.connect(self.path)
        self.assertEqual(budget.snapshot(self.conn)["held_usd"],"8")
        with self.assertRaises(budget.BudgetDenied):
            budget.reserve(self.conn,"r2","3")
        with self.assertRaises(budget.BudgetDenied):
            budget.settle(self.conn,"r1","2")

    def test_cap_escalation_denied(self):
        with self.assertRaises(budget.BudgetDenied):
            budget.initialize(self.conn,"11")
        budget.initialize(self.conn,"9")

    def test_cannot_lower_cap_below_existing_holds(self):
        budget.reserve(self.conn,"r1","8")
        with self.assertRaises(budget.BudgetDenied):
            budget.initialize(self.conn,"7")
        self.assertEqual(budget.snapshot(self.conn)["cap_usd"],"10")

    def test_bad_amounts_denied(self):
        for amount in ("NaN","Infinity","-1","0.0000000001",True,1.5):
            with self.subTest(amount=amount),self.assertRaises(budget.BudgetDenied):
                budget.units(amount)

    def test_overcharge_denied(self):
        budget.reserve(self.conn,"r1","2")
        with self.assertRaises(budget.BudgetDenied):
            budget.settle(self.conn,"r1","3")

if __name__=="__main__":
    unittest.main()
