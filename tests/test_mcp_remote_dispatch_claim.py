"""Offline contract tests for atomic single-winner dispatch claims."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_dispatch_claim import claim_dispatch, DispatchClaimDenied

class Cursor:
    def __init__(self, row):
        self.row=row
        self.sql=None
        self.args=None
    def execute(self, sql, args):
        self.sql,self.args=sql,args
    def fetchone(self):
        return self.row

class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.tenant,self.request=str(uuid4()),str(uuid4())
    def claim(self, cursor, **kw):
        params=dict(tenant_id=self.tenant,request_id=self.request,
                    idempotency_key="claim-test-0001")
        params.update(kw)
        return claim_dispatch(cursor,**params)
    def test_single_winner_cas_query(self):
        cur=Cursor((self.request,))
        result=self.claim(cur)
        self.assertEqual(result.request_id,self.request)
        self.assertIn("state = 'reserved'",cur.sql)
        self.assertIn("state = 'dispatched'",cur.sql)
        self.assertIn("tenant_id = %s",cur.sql)
        self.assertEqual(cur.args,(self.tenant,self.request,"claim-test-0001"))
    def test_missing_or_already_claimed_fails_closed(self):
        for row in (None,(str(uuid4()),)):
            with self.subTest(row=row),self.assertRaises(DispatchClaimDenied):
                self.claim(Cursor(row))
    def test_schema_invalid_keys_are_rejected_without_sql(self):
        for key in ("short", "bad/key-00001", " bad-key-00001",
                    "bad\\nkey-00001", "a" * 129, 42, True):
            with self.subTest(key=key):
                cur = Cursor((self.request,))
                with self.assertRaises(DispatchClaimDenied):
                    self.claim(cur, idempotency_key=key)
                self.assertIsNone(cur.sql)

    def test_noncanonical_identifiers_are_rejected_without_sql(self):
        from uuid import UUID
        for kw in (dict(tenant_id=self.tenant.upper()),
                   dict(request_id=UUID(self.request)),
                   dict(tenant_id=None), dict(request_id=True)):
            with self.subTest(kw=kw):
                cur = Cursor((self.request,))
                with self.assertRaises(DispatchClaimDenied):
                    self.claim(cur, **kw)
                self.assertIsNone(cur.sql)

    def test_invalid_identity_and_key_rejected_before_sql(self):
        for kw in (dict(tenant_id="bad"),dict(request_id="bad"),
                   dict(idempotency_key=""),dict(idempotency_key=None)):
            cur=Cursor((self.request,))
            with self.subTest(kw=kw),self.assertRaises(DispatchClaimDenied):
                self.claim(cur,**kw)
            self.assertIsNone(cur.sql)

if __name__ == "__main__":
    unittest.main()
