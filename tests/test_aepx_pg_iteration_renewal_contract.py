"""Static fail-closed PostgreSQL lease-renewal contracts."""
import unittest
from pathlib import Path
SQL=(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend/sql/aepx_iteration_fenced.sql").read_text()
class LeaseRenewalTests(unittest.TestCase):
    def test_renewal_requires_current_owner_fence_and_unexpired_lease(self):
        renewal=SQL.split("FUNCTION aepx_iteration.renew(",1)[1]
        for token in ("FOR UPDATE","w.lease_owner IS DISTINCT FROM p_owner",
                      "w.fence IS DISTINCT FROM p_fence",
                      "w.lease_expires_at<=clock_timestamp()",
                      "w.stage='completed'","stale or expired iteration lease"):
            with self.subTest(token=token): self.assertIn(token,renewal)
    def test_bounded_renewal_and_no_fence_change(self):
        renewal=SQL.split("FUNCTION aepx_iteration.renew(",1)[1]
        self.assertIn("p_seconds NOT BETWEEN 1 AND 600",renewal)
        self.assertIn("new_expiry:=clock_timestamp()+make_interval(secs=>p_seconds)",renewal)
        self.assertNotIn("SET fence=",renewal)
        self.assertIn("REVOKE ALL ON FUNCTION aepx_iteration.renew",renewal)
if __name__=="__main__": unittest.main()
