"""Offline SQL contract for settled reservation replay safety."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=(ROOT/"platform/saas-ide/backend/sql/aepx_budget_transactional.sql").read_text()
ACCEPTANCE=(ROOT/"tests/sql/aepx_budget_pg_acceptance.sql").read_text()

class SettledReplayTests(unittest.TestCase):
    def test_reserve_distinguishes_settled_state(self):
        reserve=SCHEMA.split("CREATE OR REPLACE FUNCTION aepx_budget.reserve(",1)[1].split("CREATE OR REPLACE FUNCTION aepx_budget.settle(",1)[0]
        self.assertIn("IF e.state = 'settled' THEN",reserve)
        self.assertIn("RETURN 'already_settled';",reserve)
        self.assertLess(reserve.index("IF e.state = 'settled' THEN"),reserve.index("RETURN 'already_reserved';"))

    def test_acceptance_exercises_post_settlement_reserve(self):
        self.assertIn("result := aepx_budget.reserve(tenant,'acceptance-1',40,'4.000000');",ACCEPTANCE)
        self.assertIn("settled reservation replay was not blocked",ACCEPTANCE)

if __name__=="__main__":
    unittest.main()
