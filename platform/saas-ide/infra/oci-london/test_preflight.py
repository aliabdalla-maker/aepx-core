import unittest
from preflight import check

class PreflightTests(unittest.TestCase):
    def test_fails_closed_on_empty_input(self):
        self.assertGreater(len(check({})), 3)

    def test_rejects_public_ip(self):
        d = dict(region="uk-london-1", compartment_ocid="ocid1.compartment.oc1..abc",
                 image_ocid="ocid1.image.oc1..abc", availability_domain="AD-1",
                 operator_approved=True, security_review_approved=True,
                 cost_review_approved=True, estimated_monthly_gbp=25,
                 budget_cap_gbp=30, public_ip_enabled=True,
                 automatic_mcp_dispatch_enabled=False, terraform_plan_reviewed=True)
        self.assertIn("Public IP prohibited for staging", check(d))
        d["public_ip_enabled"] = False
        self.assertEqual(check(d), [])
        d["estimated_monthly_gbp"] = 31
        self.assertIn("Estimated cost exceeds approved budget", check(d))

if __name__ == "__main__":
    unittest.main()
