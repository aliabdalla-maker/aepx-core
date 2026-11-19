"""Static regression for fail-closed untrusted runtime function grants."""
from pathlib import Path
import unittest
SQL=Path(__file__).resolve().parents[1]/"tests/sql/aepx_runtime_function_grant_audit.sql"
class SensitiveFunctionExecuteTests(unittest.TestCase):
 def test_runtime_execute_is_denied_not_merely_reported(self):
  source=SQL.read_text()
  self.assertIn("IF has_function_privilege(current_user,fn.oid,'EXECUTE') THEN",source)
  self.assertIn("RAISE EXCEPTION 'DENY: untrusted runtime role can execute sensitive function",source)
  self.assertIn("IF function_count < 4 THEN",source)
  self.assertNotIn("runtime EXECUTE=%",source)
if __name__=="__main__": unittest.main()
