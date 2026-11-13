"""Real PostgreSQL privilege assertions; opt-in isolated local database only."""
import os
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=[
 "20261113_hitl_identity_authority.sql",
 "20261113_hitl_identity_revision.sql",
 "20261113_hitl_identity_least_privilege.sql",
]

@unittest.skipUnless(
 os.getenv("HITL_ROLE_TEST_ISOLATED")=="yes" and os.getenv("HITL_ROLE_TEST_DSN"),
 "explicit isolated PostgreSQL role test opt-in required")
class RolePrivilegeAcceptance(unittest.TestCase):
    def test_reader_and_publisher_privileges(self):
        import psycopg
        with psycopg.connect(os.environ["HITL_ROLE_TEST_DSN"],connect_timeout=5) as conn:
            if conn.info.host not in ("localhost","127.0.0.1","::1"):
                raise RuntimeError("local PostgreSQL required")
            if conn.execute("SELECT current_database()").fetchone()[0]!="identity_test":
                raise RuntimeError("identity_test database required")
            # The test deliberately does not assume existing schema or roles.
            for migration in MIGRATIONS:
                sql=(ROOT/"services/governance/migrations"/migration).read_text()
                conn.execute(sql)
            conn.commit()
            reader="aepx_hitl_identity_reader"
            publisher="aepx_hitl_identity_publisher"
            for table in ("identity_memberships","identity_revocations","identity_authority_sync"):
                relation="hitl."+table
                for privilege in ("INSERT","UPDATE","DELETE","TRUNCATE","REFERENCES","TRIGGER"):
                    allowed=conn.execute("SELECT has_table_privilege(%s,%s,%s)",
                                         (reader,relation,privilege)).fetchone()[0]
                    self.assertFalse(allowed,(reader,relation,privilege))
                self.assertTrue(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT')",
                                             (reader,relation)).fetchone()[0])
                self.assertTrue(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT')",
                                             (publisher,relation)).fetchone()[0])
                self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'TRUNCATE')",
                                              (publisher,relation)).fetchone()[0])
            self.assertFalse(conn.execute(
                "SELECT has_schema_privilege(%s,'hitl','CREATE')",(reader,)).fetchone()[0])
            self.assertFalse(conn.execute(
                "SELECT has_schema_privilege(%s,'hitl','CREATE')",(publisher,)).fetchone()[0])
            for role in (reader,publisher):
                self.assertFalse(conn.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname=%s",
                                              (role,)).fetchone()[0])
if __name__=="__main__":
    unittest.main()
