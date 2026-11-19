"""Offline SQLite authorization ledger lifecycle regressions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.aepx_authz_nonce_ledger import consume_once
from scripts.aepx_trusted_tenant_context import sign_context,AuthorizationDenied
KEY=b"z"*32
CLAIMS={"tenant_id":"11111111-1111-4111-8111-111111111111",
 "principal_id":"service-1","audience":"aepx-db-controller",
 "action":"iteration.advance","issued_at":100,"expires_at":200,"nonce":"one"}
def consume(path,now=150):
 return consume_once(path,CLAIMS,sign_context(CLAIMS,KEY),KEY,
                     CLAIMS["tenant_id"],"service-1","iteration.advance",now=now)
class LedgerLifecycleTests(unittest.TestCase):
 def test_connection_closed_after_success_and_replay(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"nonce.db"
   connections=[]
   real_connect=sqlite3.connect
   class Wrapped:
    def __init__(self,connection):
     self.connection=connection
     self.closed=False
    def __getattr__(self,name): return getattr(self.connection,name)
    def close(self):
     self.closed=True
     self.connection.close()
   def connect(*args,**kwargs):
    wrapped=Wrapped(real_connect(*args,**kwargs))
    connections.append(wrapped)
    return wrapped
   with patch("scripts.aepx_authz_nonce_ledger.sqlite3.connect",side_effect=connect):
    self.assertTrue(consume(path))
    with self.assertRaises(AuthorizationDenied): consume(path)
   self.assertEqual(len(connections),2)
   self.assertTrue(all(connection.closed for connection in connections))
 def test_invalid_boolean_clock_denied(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(AuthorizationDenied): consume(Path(d)/"nonce.db",now=True)
if __name__=="__main__": unittest.main()
