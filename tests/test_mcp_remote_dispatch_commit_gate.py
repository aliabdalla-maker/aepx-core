"""Offline regression tests for the post-commit dispatch eligibility gate."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_dispatch_commit_gate import verify_committed_intent, DispatchNotCommitted

class Cursor:
    def __init__(self, row):
        self.row=row
        self.sql=None
        self.args=None
    def execute(self, sql, args):
        self.sql, self.args=sql,args
    def fetchone(self):
        return self.row

class CommitGateTests(unittest.TestCase):
    def setUp(self):
        self.tenant,self.request=str(uuid4()),str(uuid4())
    def verify(self, cursor, **overrides):
        params=dict(tenant_id=self.tenant,request_id=self.request,
                    idempotency_key="commit-test-0001")
        params.update(overrides)
        return verify_committed_intent(cursor,**params)
    def test_reserved_row_only(self):
        cursor=Cursor(("reserved",))
        result=self.verify(cursor)
        self.assertEqual(result.request_id,self.request)
        self.assertIn("tenant_id = %s",cursor.sql)
        self.assertIn("idempotency_key = %s",cursor.sql)
        self.assertEqual(cursor.args,(self.tenant,self.request,"commit-test-0001"))
    def test_missing_or_nonreserved_rejected(self):
        for row in (None,("dispatched",),("uncertain",),("succeeded",),("failed",)):
            with self.subTest(row=row),self.assertRaises(DispatchNotCommitted):
                self.verify(Cursor(row))
    def test_bad_identity_or_key_rejected(self):
        for overrides in (dict(tenant_id="invalid"),dict(request_id="invalid"),
                          dict(idempotency_key=""),dict(idempotency_key=None)):
            with self.subTest(overrides=overrides),self.assertRaises(DispatchNotCommitted):
                self.verify(Cursor(("reserved",)),**overrides)

if __name__ == "__main__":
    unittest.main()
