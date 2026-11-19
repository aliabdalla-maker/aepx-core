"""Static regression for truthful SECURITY DEFINER audit coverage."""
import unittest
from pathlib import Path
S=(Path(__file__).resolve().parents[1]/"tests/sql/aepx_security_definer_audit.sql").read_text()
class DefinerCoverageContract(unittest.TestCase):
 def test_missing_schemas_fail(self):
  self.assertIn("schema_count <> 2",S)
  self.assertIn("required AEP-X schemas missing",S)
 def test_zero_functions_not_claimed_as_pass(self):
  self.assertIn("inspected integer := 0",S)
  self.assertIn("inspected := inspected + 1",S)
  self.assertIn("IF inspected=0 THEN",S)
  self.assertIn("NOT ASSESSED: zero SECURITY DEFINER functions found",S)
  self.assertIn("PASS: inspected % SECURITY DEFINER functions",S)
 def test_privilege_guards_remain(self):
  for token in ("p.prosecdef","search_path=","a.grantee=0",
                "a.privilege_type='EXECUTE'","pg_has_role"):
   self.assertIn(token,S)
if __name__=="__main__": unittest.main()
