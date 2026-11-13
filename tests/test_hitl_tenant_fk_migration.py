import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"db/migrations/20261113_hitl_tenant_fk.sql").read_text()
class TenantFKMigrationTests(unittest.TestCase):
    def test_fails_on_existing_cross_tenant_events(self):
        self.assertIn("a.tenant_id<>e.tenant_id",SQL)
        self.assertIn("RAISE EXCEPTION",SQL)
    def test_composite_fk(self):
        self.assertIn("FOREIGN KEY (tenant_id,approval_id)",SQL)
        self.assertIn("REFERENCES hitl.approvals(tenant_id,id)",SQL)
    def test_validation_not_deferred(self):
        self.assertIn("VALIDATE CONSTRAINT events_tenant_approval_fk",SQL)
    def test_transactional(self):
        self.assertIn("BEGIN;",SQL)
        self.assertIn("COMMIT;",SQL)
if __name__=="__main__":unittest.main()
