"""Offline guardrail tests for opt-in PostgreSQL iteration acceptance."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_iteration_pg_acceptance.sql").read_text()
SHELL=(ROOT/"scripts/test_aepx_pg_iteration_acceptance.sh").read_text()

class PgIterationAcceptanceContract(unittest.TestCase):
    def test_rollback_and_rls_preflight(self):
        self.assertIn("rolsuper OR rolbypassrls",SQL)
        self.assertIn("relforcerowsecurity",SQL)
        self.assertLess(SQL.index("rolsuper OR rolbypassrls"),SQL.index("\nBEGIN;"))
        self.assertTrue(SQL.rstrip().endswith("ROLLBACK;"))
    def test_lifecycle_and_cross_tenant(self):
        for term in ("aepx_iteration.claim(", "aepx_iteration.renew(",
                     "aepx_iteration.advance(", "stale fence transition accepted",
                     "expired renewal accepted","cross-tenant work item visible"):
            with self.subTest(term=term): self.assertIn(term,SQL)
    def test_launcher_is_opt_in_and_local(self):
        for term in ('"--execute"',"^aepx_test_","PGHOST=127.0.0.1",
                     "ON_ERROR_STOP=1","aepx_iteration_pg_acceptance.sql"):
            with self.subTest(term=term): self.assertIn(term,SHELL)
        self.assertNotIn("CREATE DATABASE",SHELL)
if __name__=="__main__": unittest.main()
