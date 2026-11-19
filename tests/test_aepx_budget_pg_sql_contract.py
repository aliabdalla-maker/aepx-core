"""Static SQL safety contract, no database or cloud required."""
import unittest
from pathlib import Path

SQL=(Path(__file__).resolve().parents[1] /
     "platform/saas-ide/backend/sql/aepx_budget_transactional.sql").read_text()

class BudgetSQLContract(unittest.TestCase):
    def test_rls_is_forced_on_both_tables(self):
        for name in ("tenant_budget", "reservation"):
            self.assertIn(f"ALTER TABLE aepx_budget.{name} ENABLE ROW LEVEL SECURITY", SQL)
            self.assertIn(f"ALTER TABLE aepx_budget.{name} FORCE ROW LEVEL SECURITY", SQL)

    def test_transactional_locking_and_idempotency(self):
        for token in ("FOR UPDATE", "already_reserved", "already_settled",
                      "conflicting request id", "conflicting settlement",
                      "budget exhausted", "settlement exceeds reservation"):
            self.assertIn(token, SQL)

    def test_tenant_scope_and_no_implicit_provision(self):
        self.assertIn("current_setting('app.tenant_id',true)", SQL)
        self.assertIn("tenant budget missing", SQL)
        self.assertIn("PRIMARY KEY (tenant_id,request_id)", SQL)

    def test_no_public_function_execution(self):
        self.assertIn("REVOKE ALL ON FUNCTION aepx_budget.reserve", SQL)
        self.assertIn("REVOKE ALL ON FUNCTION aepx_budget.settle", SQL)

if __name__=="__main__":
    unittest.main()
