import importlib.util
import pathlib
import unittest
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-hitl-migration-check.py"
spec=importlib.util.spec_from_file_location("aepx_hitl_migration_check",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MigrationSecurityTests(unittest.TestCase):
    def test_current_migration(self):
        self.assertEqual(m.inspect(m.MIGRATION.read_text()),[])
    def test_missing_tenant_checks_fail(self):
        sql=m.MIGRATION.read_text().replace("WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)","")
        self.assertTrue(m.inspect(sql))
    def test_missing_forced_rls_fails(self):
        sql=m.MIGRATION.read_text().replace("ALTER TABLE hitl.outbox FORCE ROW LEVEL SECURITY;","")
        self.assertTrue(any("FORCE" in x for x in m.inspect(sql)))
    def test_missing_idempotency_constraint_fails(self):
        sql=m.MIGRATION.read_text().replace("UNIQUE(tenant_id,idempotency_key)","")
        self.assertTrue(any("idempotency" in x for x in m.inspect(sql)))
if __name__=="__main__":unittest.main()
