import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_jwt_shared import decode_verified_jwt,TokenVerificationDenied

class SharedJWTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.public=cls.private.public_key()
    def setUp(self):
        now=int(time.time())
        self.claims=dict(iss="https://id.example",aud="aepx",sub="reviewer-123",
            tenant_id=str(uuid4()),iat=now-10,nbf=now-10,exp=now+300)
        self.client=Mock()
        self.client.get_signing_key_from_jwt.return_value=Mock(key=self.public)
        self.config=dict(issuer="https://id.example",audience="aepx",
            jwks_url="https://id.example/jwks",key_client=self.client)
    def token(self,claims=None,key=None):
        return jwt.encode(claims or self.claims,key or self.private,algorithm="RS256")
    def test_valid_signature(self):
        self.assertEqual(decode_verified_jwt(self.token(),**self.config)["sub"],"reviewer-123")
    def test_bad_signature(self):
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with self.assertRaises(TokenVerificationDenied):
            decode_verified_jwt(self.token(key=other),**self.config)
    def test_bad_audience(self):
        with self.assertRaises(TokenVerificationDenied):
            decode_verified_jwt(self.token(self.claims|{"aud":"other"}),**self.config)
    def test_cross_host_jwks(self):
        with self.assertRaises(TokenVerificationDenied):
            decode_verified_jwt(self.token(),**(self.config|{"jwks_url":"https://evil.example/jwks"}))
    def test_missing_nbf(self):
        claims=self.claims.copy()
        del claims["nbf"]
        with self.assertRaises(TokenVerificationDenied):
            decode_verified_jwt(self.token(claims),**self.config)
if __name__=="__main__":
    unittest.main()
