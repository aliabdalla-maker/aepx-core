"""Static regression: PostgreSQL pg_has_role must use oid/oid signature."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
FILES=(
 "tests/sql/aepx_runtime_role_privilege_audit.sql",
 "tests/sql/aepx_runtime_function_grant_audit.sql",
 "tests/sql/aepx_security_definer_audit.sql",
)
class RoleMembershipSignatureTests(unittest.TestCase):
 def test_audit_calls_resolve_to_oid_oid_overload(self):
  for path in FILES:
   with self.subTest(path=path):
    source=(ROOT/path).read_text()
    self.assertIn("pg_has_role((SELECT oid FROM pg_roles WHERE rolname=",source)
    self.assertNotIn("pg_has_role(current_user,",source)
    self.assertNotIn("pg_has_role(role_name,",source)
    self.assertIn(",'MEMBER')",source)
if __name__=="__main__": unittest.main()
