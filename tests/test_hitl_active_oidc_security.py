import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_oidc import verify_bearer,AuthenticationDenied

class ActiveHITLOIDCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.public=cls.private.public_key()
    def setUp(self):
        self.now=int(time.time())
        self.env=dict(HITL_OIDC_ISSUER="https://id.example",
            HITL_OIDC_AUDIENCE="aepx-governance",
            HITL_OIDC_JWKS_URL="https://id.example/jwks")
        self.claims=dict(sub="reviewer-123",tenant_id=str(uuid4()),
            iss="https://id.example",aud="aepx-governance",
            roles=["hitl:approve"],iat=self.now-10,nbf=self.now-10,exp=self.now+600)
        self.client=Mock()
        self.client.get_signing_key_from_jwt.return_value=Mock(key=self.public)
    def token(self,claims=None,key=None,algorithm="RS256"):
        return jwt.encode(claims or self.claims,key or self.private,algorithm=algorithm)
    def check(self,token):
        return verify_bearer("Bearer "+token,env=self.env,key_client=self.client)
    def test_valid_rs256(self):
        self.assertEqual(self.check(self.token()).subject,"reviewer-123")
    def test_expired(self):
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token(self.claims|{"exp":self.now-1}))
    def test_wrong_issuer(self):
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token(self.claims|{"iss":"https://evil.example"}))
    def test_wrong_signature(self):
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token(key=other))
    def test_missing_nbf(self):
        claims=self.claims.copy()
        del claims["nbf"]
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token(claims))
    def test_cross_host_jwks(self):
        self.env["HITL_OIDC_JWKS_URL"]="https://other.example/jwks"
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token())
    def test_wrong_tenant_claim(self):
        with self.assertRaises(AuthenticationDenied):
            self.check(self.token(self.claims|{"tenant_id":"invalid"}))
if __name__=="__main__":
    unittest.main()
