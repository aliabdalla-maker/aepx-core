"""Offline least-privilege migration contract regression."""
from pathlib import Path
import unittest

MIGRATION=(Path(__file__).resolve().parents[1]/
 "services/governance/migrations/20261113_hitl_identity_least_privilege.sql")

class IdentityRoleContract(unittest.TestCase):
    def setUp(self):
        self.sql=MIGRATION.read_text()
    def test_reader_has_only_select(self):
        self.assertIn("GRANT SELECT ON TABLE",self.sql)
        self.assertIn("TO aepx_hitl_identity_reader;",self.sql)
        self.assertIn("REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER",self.sql)
    def test_publisher_has_no_truncate(self):
        self.assertIn("FROM aepx_hitl_identity_publisher;",self.sql)
        self.assertIn("REVOKE TRUNCATE,REFERENCES,TRIGGER",self.sql)
    def test_no_login_role_creation(self):
        self.assertEqual(self.sql.count("CREATE ROLE aepx_hitl_identity_"),2)
        self.assertEqual(self.sql.count(" NOLOGIN NOSUPERUSER"),2)
    def test_public_table_access_revoked(self):
        self.assertIn("hitl.identity_authority_sync FROM PUBLIC;",self.sql)
if __name__=="__main__":
    unittest.main()
