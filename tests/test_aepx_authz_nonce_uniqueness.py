"""Regression tests for scoped nonce uniqueness independent of signing key."""
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_authz_nonce_ledger import consume_once
from scripts.aepx_trusted_tenant_context import sign_context,AuthorizationDenied
CLAIMS={"tenant_id":"11111111-1111-4111-8111-111111111111",
 "principal_id":"service-1","audience":"aepx-db-controller",
 "action":"iteration.advance","issued_at":100,"expires_at":200,"nonce":"fixed-nonce"}
def consume(path,claims,key):
 return consume_once(path,claims,sign_context(claims,key),key,
                     claims["tenant_id"],claims["principal_id"],claims["action"],now=150)
class NonceUniquenessTests(unittest.TestCase):
 def test_different_signing_keys_same_nonce_denied(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"ledger.db"
   self.assertTrue(consume(path,CLAIMS,b"a"*32))
   with self.assertRaises(AuthorizationDenied):
    consume(path,CLAIMS,b"b"*32)
 def test_changed_validity_same_nonce_denied(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"ledger.db"
   self.assertTrue(consume(path,CLAIMS,b"a"*32))
   other=dict(CLAIMS);other["expires_at"]=201
   with self.assertRaises(AuthorizationDenied):
    consume(path,other,b"a"*32)
 def test_different_nonce_allowed(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"ledger.db"
   self.assertTrue(consume(path,CLAIMS,b"a"*32))
   other=dict(CLAIMS);other["nonce"]="different-nonce"
   self.assertTrue(consume(path,other,b"a"*32))
if __name__=="__main__": unittest.main()
