import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_verified_jti import enforce_verified_claims_identity
from app.hitl_identity_policy import IdentityPolicyDenied

class VerifiedJtiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tenant=str(uuid4())
        self.claims={"sub":"operator-123","iss":"https://identity.example",
            "jti":"verified-jti-123","tenant_id":self.tenant}
        self.args={"verified_claims":self.claims,"connection_factory":lambda:None,
            "expected_tenant":self.tenant}
    @patch("app.hitl_verified_jti.enforce_postgres_identity",return_value=True)
    def test_verified_claims_forwarded(self,verify):
        self.assertTrue(enforce_verified_claims_identity(**self.args))
        self.assertEqual(verify.call_args.kwargs["token_id"],"verified-jti-123")
    def test_missing_jti_denied(self):
        del self.claims["jti"]
        with self.assertRaises(IdentityPolicyDenied):
            enforce_verified_claims_identity(**self.args)
    def test_cross_tenant_denied(self):
        self.args["expected_tenant"]=str(uuid4())
        with self.assertRaises(IdentityPolicyDenied):
            enforce_verified_claims_identity(**self.args)
    def test_invalid_jti_denied(self):
        self.claims["jti"]="short"
        with self.assertRaises(IdentityPolicyDenied):
            enforce_verified_claims_identity(**self.args)
    def test_unverified_input_type_denied(self):
        self.args["verified_claims"]="raw-token"
        with self.assertRaises(IdentityPolicyDenied):
            enforce_verified_claims_identity(**self.args)
    @patch("app.hitl_verified_jti.enforce_postgres_identity",side_effect=RuntimeError())
    def test_database_failure_denied(self,verify):
        with self.assertRaises(IdentityPolicyDenied):
            enforce_verified_claims_identity(**self.args)
if __name__=="__main__":
    unittest.main()
