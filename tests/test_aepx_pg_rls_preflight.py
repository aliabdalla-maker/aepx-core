"""Static guardrails for PostgreSQL acceptance RLS preflight."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "tests/sql/aepx_budget_pg_acceptance.sql"

class PgRlsPreflightTests(unittest.TestCase):
    def test_preflight_precedes_fixture_transaction(self):
        source=SQL.read_text()
        self.assertLess(source.index("rolsuper OR rolbypassrls"),source.index("\nBEGIN;"))
        self.assertLess(source.index("relforcerowsecurity"),source.index("\nBEGIN;"))
        self.assertLess(source.index("aepx_budget.reservation'::regclass"),source.index("\nBEGIN;"))
        self.assertLess(source.index("\nBEGIN;"),source.index("INSERT INTO aepx_budget.tenant_budget"))

    def test_preflight_is_fail_closed(self):
        source=SQL.read_text()
        self.assertIn("role_bypass IS DISTINCT FROM false",source)
        self.assertIn("force_budget IS DISTINCT FROM true",source)
        self.assertIn("force_reservation IS DISTINCT FROM true",source)
        self.assertIn("rls_budget IS DISTINCT FROM true",source)
        self.assertIn("rls_reservation IS DISTINCT FROM true",source)

if __name__=="__main__":
    unittest.main()
