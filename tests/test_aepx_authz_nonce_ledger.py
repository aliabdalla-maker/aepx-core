"""Offline authorization replay ledger tests."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from scripts.aepx_authz_nonce_ledger import consume_once
from scripts.aepx_trusted_tenant_context import sign_context,AuthorizationDenied
KEY=b"q"*32
CLAIMS={"tenant_id":"11111111-1111-4111-8111-111111111111",
 "principal_id":"service-1","audience":"aepx-db-controller",
 "action":"iteration.advance","issued_at":100,"expires_at":200,
 "nonce":"unique-1"}
def consume(path,claims=CLAIMS,signature=None):
 return consume_once(path,claims,signature or sign_context(claims,KEY),KEY,
                     CLAIMS["tenant_id"],"service-1","iteration.advance",now=150)
class NonceLedgerTests(unittest.TestCase):
 def test_replay_denied_across_connections(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"nonce.sqlite"
   self.assertTrue(consume(path))
   with self.assertRaises(AuthorizationDenied): consume(path)
 def test_concurrent_only_one_succeeds(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"nonce.sqlite"
   def attempt(_):
    try: return consume(path)
    except AuthorizationDenied: return False
   with ThreadPoolExecutor(max_workers=8) as pool:
    results=list(pool.map(attempt,range(8)))
   self.assertEqual(results.count(True),1)
 def test_tamper_and_expiry_denied(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"nonce.sqlite"
   altered=dict(CLAIMS);altered["principal_id"]="other"
   with self.assertRaises(AuthorizationDenied):
    consume(path,altered,sign_context(CLAIMS,KEY))
   with self.assertRaises(AuthorizationDenied):
    consume_once(path,CLAIMS,sign_context(CLAIMS,KEY),KEY,
                 CLAIMS["tenant_id"],"service-1","iteration.advance",now=200)
 def test_reject_directory_path(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AuthorizationDenied): consume(Path(d))
if __name__=="__main__": unittest.main()
