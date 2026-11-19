"""Offline static contracts for PostgreSQL iteration fencing."""
import unittest
from pathlib import Path

SQL=(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend/sql/aepx_iteration_fenced.sql").read_text()

class PgIterationFenceTests(unittest.TestCase):
    def test_tenant_rls_forced(self):
        self.assertIn("ENABLE ROW LEVEL SECURITY",SQL)
        self.assertIn("FORCE ROW LEVEL SECURITY",SQL)
        self.assertIn("current_setting('app.tenant_id',true)",SQL)
        self.assertIn("SECURITY INVOKER",SQL)
    def test_claim_serializes_and_increments_fence(self):
        claim=SQL.split("FUNCTION aepx_iteration.claim(",1)[1].split("FUNCTION aepx_iteration.advance(",1)[0]
        self.assertIn("FOR UPDATE",claim)
        self.assertIn("lease_expires_at>clock_timestamp()",claim)
        self.assertIn("fence=fence+1",claim)
        self.assertIn("iteration lease active",claim)
    def test_advance_rejects_stale_and_out_of_order(self):
        advance=SQL.split("FUNCTION aepx_iteration.advance(",1)[1]
        self.assertIn("FOR UPDATE",advance)
        self.assertIn("w.fence IS DISTINCT FROM p_fence",advance)
        self.assertIn("w.lease_expires_at<=clock_timestamp()",advance)
        self.assertIn("out-of-order iteration transition",advance)
        self.assertIn("WHEN 'reviewed' THEN 'completed'",advance)
    def test_no_implicit_provision_or_provider_execution(self):
        self.assertNotIn("INSERT INTO aepx_iteration.work_item",SQL)
        self.assertNotIn("http_",SQL)
        self.assertIn("REVOKE ALL ON FUNCTION aepx_iteration.advance",SQL)

if __name__=="__main__": unittest.main()
