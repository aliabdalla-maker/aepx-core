"""Offline fail-closed tests for ambiguous MCP dispatch reconciliation."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_reconciliation import mark_stale_dispatch_uncertain, ReconciliationDenied

class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None
    def execute(self, query, params):
        self.query, self.params = query, params
    def fetchone(self):
        return self.row

class ReconciliationTests(unittest.TestCase):
    def test_stale_dispatch_quarantined_with_atomic_predicate(self):
        request = str(uuid4())
        tenant = str(uuid4())
        cur = FakeCursor((request,))
        self.assertEqual(mark_stale_dispatch_uncertain(cur, tenant_id=tenant,
            request_id=request, minimum_age_seconds=60), "uncertain")
        self.assertIn("state = 'dispatched'", cur.query)
        self.assertIn("state = 'uncertain'", cur.query)
        self.assertIn("updated_at <=", cur.query)
        self.assertEqual(cur.params, (tenant, request, 60))

    def test_no_row_fails_closed(self):
        with self.assertRaises(ReconciliationDenied):
            mark_stale_dispatch_uncertain(FakeCursor(None), tenant_id=str(uuid4()),
                request_id=str(uuid4()), minimum_age_seconds=60)

    def test_invalid_age_fails_closed(self):
        for age in (0, -1, 86401, True, 1.5, "60"):
            with self.subTest(age=age), self.assertRaises(ReconciliationDenied):
                mark_stale_dispatch_uncertain(FakeCursor(None), tenant_id=str(uuid4()),
                    request_id=str(uuid4()), minimum_age_seconds=age)

    def test_invalid_uuid_fails_closed(self):
        with self.assertRaises(ReconciliationDenied):
            mark_stale_dispatch_uncertain(FakeCursor(None), tenant_id="not-a-uuid",
                request_id=str(uuid4()), minimum_age_seconds=60)

    def test_invalid_inputs_never_execute_sql(self):
        from uuid import UUID
        tenant, request = str(uuid4()), str(uuid4())
        cases = (
            (UUID(tenant), request, 60),
            (tenant.upper(), request, 60),
            (tenant, UUID(request), 60),
            (tenant, request.upper(), 60),
            (tenant, request, 0),
            (tenant, request, True),
            (tenant, request, 86401),
        )
        for tenant_id, request_id, age in cases:
            with self.subTest(tenant_id=tenant_id, request_id=request_id, age=age):
                cur = FakeCursor((request,))
                with self.assertRaises(ReconciliationDenied):
                    mark_stale_dispatch_uncertain(
                        cur, tenant_id=tenant_id, request_id=request_id,
                        minimum_age_seconds=age)
                self.assertIsNone(cur.query)
                self.assertIsNone(cur.params)

    def test_mismatched_returning_row_fails_closed(self):
        request = str(uuid4())
        cur = FakeCursor((str(uuid4()),))
        with self.assertRaises(ReconciliationDenied):
            mark_stale_dispatch_uncertain(
                cur, tenant_id=str(uuid4()), request_id=request,
                minimum_age_seconds=60)

    def test_valid_reconciliation_age_boundaries(self):
        for age in (1, 86400):
            with self.subTest(age=age):
                request = str(uuid4())
                cur = FakeCursor((request,))
                self.assertEqual(
                    mark_stale_dispatch_uncertain(
                        cur, tenant_id=str(uuid4()), request_id=request,
                        minimum_age_seconds=age), "uncertain")
                self.assertEqual(cur.params[2], age)

if __name__ == "__main__":
    unittest.main()
