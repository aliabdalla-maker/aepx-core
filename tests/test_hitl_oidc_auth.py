import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_oidc_auth import verify_oidc_operator,IdentityVerificationError
from app.hitl_operator_identity import operator_verifier
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

class OIDCVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.public=cls.private.public_key()
    def setUp(self):
        self.tenant=str(uuid4())
        self.issuer="https://identity.example"
        self.audience="aepx-governance"
        self.kw=dict(issuer=self.issuer,audience=self.audience,
                     jwks_url="https://identity.example/.well-known/jwks.json",
                     now_epoch=1000)
        self.client=Mock()
        self.client.get_signing_key_from_jwt.return_value=Mock(key=self.public)
        self.claims=dict(sub="reviewer-123",tenant_id=self.tenant,iss=self.issuer,
                         aud=self.audience,iat=900,nbf=900,exp=2000,
                         permissions=["hitl.remote.reconcile"])
    def token(self,**changes):
        return jwt.encode(self.claims|changes,self.private,algorithm="RS256",
                          headers={"kid":"test-key"})
    def verify(self,token):
        return verify_oidc_operator(token,**self.kw,jwk_client=self.client)
    def test_valid_signature_and_scoped_permission(self):
        operator=self.verify(self.token())
        decision=operator_verifier(operator,trusted_issuer=self.issuer,
                                   trusted_audience=self.audience,now_epoch=1000)
        self.assertTrue(decision(tenant_id=self.tenant,event_id=str(uuid4()),
                     provider="sandbox",reviewer_id="reviewer-123",
                     permission="hitl.remote.reconcile",verified_state="confirmed"))
    def test_wrong_issuer(self):
        with self.assertRaises(IdentityVerificationError):
            self.verify(self.token(iss="https://attacker.example"))
    def test_wrong_audience(self):
        with self.assertRaises(IdentityVerificationError):
            self.verify(self.token(aud="other-service"))
    def test_missing_tenant(self):
        data=self.claims.copy()
        del data["tenant_id"]
        with self.assertRaises(IdentityVerificationError):
            self.verify(jwt.encode(data,self.private,algorithm="RS256"))
    def test_wrong_signature(self):
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with self.assertRaises(IdentityVerificationError):
            self.verify(jwt.encode(self.claims,other,algorithm="RS256"))
    def test_unsigned_token(self):
        with self.assertRaises(IdentityVerificationError):
            self.verify(jwt.encode(self.claims,key="",algorithm="none"))
    def test_missing_jwks_config(self):
        with self.assertRaises(IdentityVerificationError):
            verify_oidc_operator(self.token(),issuer=self.issuer,
                audience=self.audience,jwks_url="http://insecure.example",
                jwk_client=self.client)
    def test_expired_token(self):
        with self.assertRaises(IdentityVerificationError):
            self.verify(self.token(exp=999))
if __name__=="__main__":
    unittest.main()
