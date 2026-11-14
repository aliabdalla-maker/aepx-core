"""Static contract for PostgreSQL schema/function privilege audit."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_runtime_function_grant_audit.sql").read_text()
SH=(ROOT/"scripts/test_aepx_pg_function_grants.sh").read_text()
class FunctionGrantAuditContract(unittest.TestCase):
 def test_public_execute_and_schema_create_denied(self):
  for token in ("aclexplode","acldefault('n'","acldefault('f'",
                "a.grantee=0","a.privilege_type='CREATE'",
                "a.privilege_type='EXECUTE'","has_schema_privilege",
                "pg_has_role","rolbypassrls"):
   self.assertIn(token,SQL)
 def test_core_functions_required(self):
  for token in ("'claim'","'advance'","'renew'","'consume_approval'",
                "required iteration authorization functions missing"):
   self.assertIn(token,SQL)
 def test_guarded_read_only(self):
  for token in ("--execute","aepx_test_","PGHOSTADDR",
                "default_transaction_read_only=on","PGHOST=127.0.0.1"):
   self.assertIn(token,SH)
  self.assertNotIn("GRANT ",SQL)
  self.assertNotIn("REVOKE ",SQL)
if __name__=="__main__": unittest.main()
