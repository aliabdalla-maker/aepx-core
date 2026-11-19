import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_verified_bearer_identity import verify_bearer_identity
from app.hitl_identity_policy import IdentityPolicyDenied

class BearerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tenant=str(uuid4())
        self.env={"HITL_OIDC_ISSUER":"https://identity.example",
                  "HITL_OIDC_AUDIENCE":"aepx",
                  "HITL_OIDC_JWKS_URL":"https://identity.example/jwks"}
        self.jwt=MagicMock()
        self.key=MagicMock()
        self.key.get_signing_key_from_jwt.return_value.key="public-key"
        self.claims={"sub":"operator-123","iss":"https://identity.example",
                     "jti":"token-123456","tenant_id":self.tenant}
        self.jwt.decode.return_value=self.claims
        self.args=dict(authorization="Bearer header.payload.signature",
            expected_tenant=self.tenant,connection_factory=lambda:None,
            env=self.env,key_client=self.key,jwt_module=self.jwt)
    @patch("app.hitl_verified_bearer_identity.enforce_verified_claims_identity",return_value=True)
    def test_verified_claims_reach_policy(self,policy):
        self.assertTrue(verify_bearer_identity(**self.args))
        self.assertEqual(policy.call_args.kwargs["verified_claims"],self.claims)
        self.assertEqual(self.jwt.decode.call_args.kwargs["algorithms"],["RS256"])
        self.assertIn("jti",self.jwt.decode.call_args.kwargs["options"]["require"])
    def test_invalid_signature_denied(self):
        self.jwt.decode.side_effect=ValueError("invalid signature")
        with self.assertRaises(IdentityPolicyDenied):
            verify_bearer_identity(**self.args)
    def test_missing_jti_denied(self):
        del self.claims["jti"]
        with self.assertRaises(IdentityPolicyDenied):
            verify_bearer_identity(**self.args)
    def test_cross_tenant_denied(self):
        self.args["expected_tenant"]=str(uuid4())
        with self.assertRaises(IdentityPolicyDenied):
            verify_bearer_identity(**self.args)
    def test_untrusted_jwks_denied(self):
        self.env["HITL_OIDC_JWKS_URL"]="http://evil.example/jwks"
        with self.assertRaises(IdentityPolicyDenied):
            verify_bearer_identity(**self.args)
    def test_missing_bearer_denied(self):
        self.args["authorization"]="not a bearer"
        with self.assertRaises(IdentityPolicyDenied):
            verify_bearer_identity(**self.args)
if __name__=="__main__":
    unittest.main()
