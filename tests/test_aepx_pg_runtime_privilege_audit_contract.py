"""Offline contracts for read-only runtime role privilege audit."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_runtime_role_privilege_audit.sql").read_text()
SH=(ROOT/"scripts/test_aepx_pg_runtime_privileges.sh").read_text()
class RuntimePrivilegeAuditContract(unittest.TestCase):
 def test_all_critical_tables(self):
  for table in ("aepx_iteration.work_item","aepx_iteration.approval_nonce",
                "aepx_budget.tenant_budget","aepx_budget.reservation"):
   self.assertIn(table,SQL)
 def test_fail_closed(self):
  for token in ("rolsuper OR rolbypassrls","relforcerowsecurity",
                "pg_has_role","INSERT","UPDATE","DELETE","TRUNCATE",
                "REFERENCES","TRIGGER","RAISE EXCEPTION"):
   self.assertIn(token,SQL)
  self.assertNotIn("CREATE TABLE",SQL)
  self.assertNotIn("ALTER TABLE",SQL)
 def test_guarded_read_only_launcher(self):
  for token in ("--execute","aepx_test_","PGHOSTADDR",
                "PGOPTIONS='-c default_transaction_read_only=on'",
                "PGHOST=127.0.0.1","ON_ERROR_STOP=1"):
   self.assertIn(token,SH)
if __name__=="__main__": unittest.main()
