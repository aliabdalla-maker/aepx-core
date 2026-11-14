"""Offline structural checks for opt-in PostgreSQL acceptance artifacts."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_budget_pg_acceptance.sql").read_text()
RUNNER=(ROOT/"scripts/test_aepx_pg_budget_acceptance.sh").read_text()

class PostgreSQLAcceptanceContract(unittest.TestCase):
    def test_rollback_only_fixture(self):
        self.assertIn("BEGIN;",SQL)
        self.assertIn("ROLLBACK;",SQL)
        self.assertNotIn("COMMIT;",SQL)

    def test_critical_behaviors(self):
        for marker in ("already_reserved","budget exhausted","already_settled",
                       "conflicting settlement","cross-tenant reservation visible",
                       "cross-tenant budget row visible"):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)

    def test_runner_requires_opt_in_and_disposable_local_database(self):
        for marker in ('"--execute"',"^aepx_test_","127.0.0.1",
                       "ON_ERROR_STOP=1","PGHOSTADDR","PGSERVICE"):
            self.assertIn(marker,RUNNER)

if __name__=="__main__":
    unittest.main()
