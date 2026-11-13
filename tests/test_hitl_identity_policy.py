import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_policy import enforce_identity_policy,IdentityPolicyDenied

class IdentityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.args=dict(subject="reviewer-123",tenant_id=str(uuid4()),
            token_id="token-id-123",issuer="https://issuer.example")
    def check(self,member=None,revoked=None):
        return enforce_identity_policy(**self.args,
            verify_membership=member,verify_not_revoked=revoked)
    def test_both_authorities_allow(self):
        self.assertTrue(self.check(lambda **k: True,lambda **k: True))
    def test_missing_authorities_denied(self):
        with self.assertRaises(IdentityPolicyDenied):
            self.check()
    def test_membership_denied(self):
        with self.assertRaises(IdentityPolicyDenied):
            self.check(lambda **k: False,lambda **k: True)
    def test_revoked_denied(self):
        with self.assertRaises(IdentityPolicyDenied):
            self.check(lambda **k: True,lambda **k: False)
    def test_non_boolean_denied(self):
        with self.assertRaises(IdentityPolicyDenied):
            self.check(lambda **k: 1,lambda **k: True)
    def test_authority_outage_denied(self):
        def fail(**kw): raise TimeoutError()
        with self.assertRaises(IdentityPolicyDenied):
            self.check(fail,lambda **k: True)
    def test_invalid_tenant_denied(self):
        self.args["tenant_id"]="invalid"
        with self.assertRaises(IdentityPolicyDenied):
            self.check(lambda **k: True,lambda **k: True)
if __name__=="__main__":
    unittest.main()
