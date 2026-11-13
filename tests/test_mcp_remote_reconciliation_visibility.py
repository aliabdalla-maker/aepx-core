"""Offline tests for read-only uncertain-intent visibility."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_reconciliation_visibility import (
    list_uncertain_intents, ReconciliationVisibilityDenied)

class Cursor:
    def __init__(self, rows=()):
        self.rows, self.query, self.params = rows, None, None
    def execute(self, query, params):
        self.query, self.params = query, params
    def fetchall(self):
        return self.rows

class VisibilityTests(unittest.TestCase):
    def test_bounded_tenant_scoped_read_only(self):
        tenant, request = str(uuid4()), str(uuid4())
        cur = Cursor([(request, "key-00000001", None)])
        result = list_uncertain_intents(cur, tenant_id=tenant, limit=2)
        self.assertEqual(result[0].request_id, request)
        self.assertEqual(cur.params, (tenant, 2))
        self.assertIn("state = 'uncertain'", cur.query)
        self.assertIn("ORDER BY updated_at ASC", cur.query)
        self.assertTrue(cur.query.lstrip().startswith("SELECT"))

    def test_invalid_input_never_queries(self):
        for tenant, limit in ((str(uuid4()), 0), (str(uuid4()), 101),
                              (str(uuid4()), True), ("invalid", 1),
                              (str(uuid4()).upper(), 1)):
            with self.subTest(tenant=tenant, limit=limit):
                cur = Cursor()
                with self.assertRaises(ReconciliationVisibilityDenied):
                    list_uncertain_intents(cur, tenant_id=tenant, limit=limit)
                self.assertIsNone(cur.query)

    def test_duplicate_request_ids_fail_closed(self):
        tenant, request = str(uuid4()), str(uuid4())
        cur = Cursor([
            (request, "key-00000001", None),
            (request, "key-00000002", None),
        ])
        with self.assertRaises(ReconciliationVisibilityDenied):
            list_uncertain_intents(cur, tenant_id=tenant, limit=2)
        self.assertEqual(cur.params, (tenant, 2))

    def test_malformed_or_oversized_results_fail_closed(self):
        tenant = str(uuid4())
        valid = (str(uuid4()), "key-00000001", None)
        cases = (
            [valid, valid],
            [("not-a-uuid", "key-00000001", None)],
            [(str(uuid4()), "short", None)],
            [(str(uuid4()), "key-00000001")],
            None,
        )
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ReconciliationVisibilityDenied):
                list_uncertain_intents(Cursor(rows), tenant_id=tenant, limit=1)

if __name__ == "__main__":
    unittest.main()
