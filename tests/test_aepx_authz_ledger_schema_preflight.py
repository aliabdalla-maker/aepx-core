"""Fail-closed legacy replay-ledger schema tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_authz_nonce_ledger import consume_once
from scripts.aepx_trusted_tenant_context import sign_context,AuthorizationDenied
KEY=b"s"*32
CLAIMS={"tenant_id":"11111111-1111-4111-8111-111111111111",
 "principal_id":"service-1","audience":"aepx-db-controller",
 "action":"iteration.advance","issued_at":100,"expires_at":200,"nonce":"one"}
def consume(path):
 return consume_once(path,CLAIMS,sign_context(CLAIMS,KEY),KEY,
                     CLAIMS["tenant_id"],"service-1","iteration.advance",now=150)
class SchemaPreflightTests(unittest.TestCase):
 def test_legacy_schema_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"old.db"
   with sqlite3.connect(path) as db:
    db.execute("""CREATE TABLE consumed_context(
     fingerprint TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,
     principal_id TEXT NOT NULL,action TEXT NOT NULL,
     expires_at INTEGER NOT NULL,consumed_at INTEGER NOT NULL)""")
   with self.assertRaisesRegex(AuthorizationDenied,"incompatible"):
    consume(path)
 def test_missing_unique_nonce_index_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"weak.db"
   with sqlite3.connect(path) as db:
    db.execute("""CREATE TABLE consumed_context(
     fingerprint TEXT PRIMARY KEY,nonce TEXT NOT NULL,
     tenant_id TEXT NOT NULL,principal_id TEXT NOT NULL,
     action TEXT NOT NULL,expires_at INTEGER NOT NULL,
     consumed_at INTEGER NOT NULL)""")
   with self.assertRaisesRegex(AuthorizationDenied,"uniqueness"):
    consume(path)
 def test_fresh_schema_works(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertTrue(consume(Path(d)/"fresh.db"))
if __name__=="__main__": unittest.main()
