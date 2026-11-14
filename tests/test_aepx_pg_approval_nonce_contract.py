"""Static safety contract for staging-only approval consumption."""
import unittest
from pathlib import Path
SQL=(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend/sql/aepx_iteration_approval_nonce.sql").read_text()
class ApprovalNonceContract(unittest.TestCase):
    def test_rls_and_unique_nonce(self):
        for token in ("PRIMARY KEY (tenant_id,nonce)","ENABLE ROW LEVEL SECURITY",
                      "FORCE ROW LEVEL SECURITY","approval_nonce_tenant_scope"):
            self.assertIn(token,SQL)
    def test_atomic_fenced_single_use(self):
        fn=SQL.split("CREATE OR REPLACE FUNCTION aepx_iteration.consume_approval(",1)[1]
        for token in ("SECURITY INVOKER","FOR UPDATE","w.stage<>'reviewed'",
                      "w.fence<>p_fence","w.lease_expires_at<=clock_timestamp()",
                      "a.lease_fence<>p_fence","a.consumed_at IS NOT NULL",
                      "a.expires_at<=clock_timestamp()","SET consumed_at=clock_timestamp()",
                      "REVOKE ALL ON FUNCTION"):
            with self.subTest(token=token): self.assertIn(token,fn)
        self.assertLess(fn.index("SELECT * INTO w"),fn.index("SELECT * INTO a"))
    def test_no_completion_unlock(self):
        self.assertNotIn("SET stage='completed'",SQL)
        self.assertNotIn("CREATE OR REPLACE FUNCTION aepx_iteration.complete",SQL)
if __name__=="__main__": unittest.main()
