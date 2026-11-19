"""Offline static checks for guarded approval nonce PostgreSQL acceptance."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_approval_nonce_pg_acceptance.sql").read_text()
SCRIPT=(ROOT/"scripts/test_aepx_pg_approval_nonce_acceptance.sh").read_text()
class ApprovalAcceptanceContract(unittest.TestCase):
 def test_preflight_and_rollback(self):
  for term in ("rolsuper OR rolbypassrls","relforcerowsecurity","approval_nonce'::regclass",
               "work_item'::regclass","ROLLBACK;"):
   self.assertIn(term,SQL)
  self.assertTrue(SQL.rstrip().endswith("ROLLBACK;"))
  self.assertLess(SQL.index("rolsuper OR rolbypassrls"),SQL.index("\nBEGIN;"))
 def test_replay_expiry_fence_and_tenant(self):
  for term in ("approval replay accepted","expired approval accepted",
               "stale approval fence accepted","wrong reviewer accepted",
               "expired work lease accepted","cross-tenant nonce visible"):
   self.assertIn(term,SQL)
 def test_local_opt_in_launcher(self):
  for term in ('"--execute"',"^aepx_test_","PGHOST=127.0.0.1",
               "ON_ERROR_STOP=1","aepx_approval_nonce_pg_acceptance.sql"):
   self.assertIn(term,SCRIPT)
  self.assertNotIn("CREATE DATABASE",SCRIPT)
if __name__=="__main__": unittest.main()
