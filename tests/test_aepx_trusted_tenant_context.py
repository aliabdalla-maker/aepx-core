"""Offline tests for scoped authorization context."""
import unittest
from copy import deepcopy
from scripts.aepx_trusted_tenant_context import (
    sign_context,verify_context,AuthorizationDenied)
KEY=b"k"*32
CLAIMS={"tenant_id":"11111111-1111-4111-8111-111111111111",
        "principal_id":"service-1","audience":"aepx-db-controller",
        "action":"iteration.advance","issued_at":100,"expires_at":200,
        "nonce":"unique-1"}
class AuthzContractTests(unittest.TestCase):
 def test_valid_context(self):
  sig=sign_context(CLAIMS,KEY)
  self.assertTrue(verify_context(CLAIMS,sig,KEY,CLAIMS["tenant_id"],
                                 "service-1","iteration.advance",now=150))
 def test_tamper_and_scope_fail_closed(self):
  sig=sign_context(CLAIMS,KEY)
  for field,value in (("tenant_id","22222222-2222-4222-8222-222222222222"),
                      ("principal_id","attacker"),("action","budget.settle"),
                      ("nonce","unique-2")):
   altered=deepcopy(CLAIMS); altered[field]=value
   with self.assertRaises(AuthorizationDenied):
    verify_context(altered,sig,KEY,CLAIMS["tenant_id"],
                   "service-1","iteration.advance",now=150)
  with self.assertRaises(AuthorizationDenied):
   verify_context(CLAIMS,sig,KEY,CLAIMS["tenant_id"],
                  "attacker","iteration.advance",now=150)
 def test_expiry_future_weak_key_and_boolean_time(self):
  sig=sign_context(CLAIMS,KEY)
  for instant in (99,200,True):
   with self.assertRaises(AuthorizationDenied):
    verify_context(CLAIMS,sig,KEY,CLAIMS["tenant_id"],
                   "service-1","iteration.advance",now=instant)
  with self.assertRaises(AuthorizationDenied): sign_context(CLAIMS,b"short")
 def test_reject_unknown_fields_and_invalid_duration(self):
  for field,value in (("expires_at",401),("issued_at",True),
                      ("audience","other")):
   altered=deepcopy(CLAIMS);altered[field]=value
   with self.assertRaises(AuthorizationDenied): sign_context(altered,KEY)
  altered=deepcopy(CLAIMS);altered["trusted"]=True
  with self.assertRaises(AuthorizationDenied): sign_context(altered,KEY)
if __name__=="__main__": unittest.main()
