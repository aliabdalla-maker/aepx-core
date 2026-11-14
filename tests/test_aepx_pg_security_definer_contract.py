"""Static contract checks for PostgreSQL SECURITY DEFINER audit."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"tests/sql/aepx_security_definer_audit.sql").read_text()
SH=(ROOT/"scripts/test_aepx_pg_security_definer.sh").read_text()
class SecurityDefinerAuditContract(unittest.TestCase):
 def test_definer_search_path_and_public_execute(self):
  for token in ("p.prosecdef","proconfig","search_path=",
                "pg_catalog(, *pg_temp)?","aclexplode",
                "a.grantee=0","a.privilege_type='EXECUTE'",
                "pg_has_role","RAISE EXCEPTION"):
   self.assertIn(token,SQL)
 def test_guarded_local_read_only(self):
  for token in ("--execute","aepx_test_","PGHOSTADDR",
                "PGHOST=127.0.0.1","default_transaction_read_only=on"):
   self.assertIn(token,SH)
  self.assertNotIn("\nALTER ",SQL)
  self.assertNotIn("\nGRANT ",SQL)
if __name__=="__main__": unittest.main()
