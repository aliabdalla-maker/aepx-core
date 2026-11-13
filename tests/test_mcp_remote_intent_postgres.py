"""Disposable PostgreSQL integration tests for MCP intent reservation.

Requires AEPX_TEST_PG_DSN pointing at a throwaway DB. Never run on production.
"""
import os
import sys
import threading
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_intent_reservation import IntentReservation, reserve_intent
from app.mcp_remote_intent_schema import DDL

DSN = os.environ.get("AEPX_TEST_PG_DSN")
RUNTIME_DSN = os.environ.get("AEPX_TEST_PG_RUNTIME_DSN")
ALLOW_DISPOSABLE = os.environ.get("AEPX_ALLOW_DISPOSABLE_PG_TESTS") == "yes"
try:
    import psycopg
except ImportError:
    psycopg = None

@unittest.skipUnless(DSN and RUNTIME_DSN and psycopg and ALLOW_DISPOSABLE, "explicit disposable PostgreSQL opt-in, DSN and psycopg required")
class PostgresReservationAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tenant = str(uuid4())
        cls.intent = IntentReservation(cls.tenant, str(uuid4()), str(uuid4()),
            "a"*64, "approved-resource", "tool.read", "2025-11-25", "request-000001")
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
                cur.execute("GRANT USAGE ON SCHEMA public TO aepx_runtime")
                cur.execute("GRANT SELECT, INSERT, UPDATE ON mcp_remote_execution_intents TO aepx_runtime")

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS mcp_remote_execution_intents")

    def _reserve(self, intent, results, errors):
        try:
            with psycopg.connect(RUNTIME_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.tenant_id = %s", (intent.tenant_id,))
                    results.append(reserve_intent(cur, intent))
        except Exception as exc:
            errors.append(exc)

    def test_two_workers_single_reservation(self):
        results, errors = [], []
        from dataclasses import replace
        concurrent_intent = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()), idempotency_key="race-00000001")
        workers = [threading.Thread(target=self._reserve, args=(concurrent_intent,results,errors))
                   for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=15)
        self.assertFalse(any(worker.is_alive() for worker in workers), "worker hung")
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(results, ["created", "existing"])

    def test_conflicting_request_key_rejected(self):
        from dataclasses import replace
        from app.mcp_remote_intent_reservation import ReservationDenied
        conflicting = replace(self.intent, tool_name="tool.delete")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.tenant_id = %s", (self.tenant,))
                reserve_intent(cur, self.intent)
                with self.assertRaises(ReservationDenied):
                    reserve_intent(cur, conflicting)

    def test_cross_tenant_write_rejected(self):
        other_tenant = str(uuid4())
        candidate = IntentReservation(self.tenant, str(uuid4()), str(uuid4()),
            "b"*64, "resource-other", "tool.read", "2025-11-25", "cross-tenant-0001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.tenant_id = %s", (other_tenant,))
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    reserve_intent(cur, candidate)

    def test_runtime_without_tenant_context_cannot_insert(self):
        candidate = IntentReservation(self.tenant, str(uuid4()), str(uuid4()),
            "c"*64, "resource-unscoped", "tool.read", "2025-11-25", "unscoped-000001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    reserve_intent(cur, candidate)

    def test_cross_tenant_read_denied(self):
        seed = IntentReservation(self.tenant, str(uuid4()), str(uuid4()),
            "d"*64, "resource-seed", "tool.read", "2025-11-25", "read-seed-00001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.tenant_id = %s", (self.tenant,))
                reserve_intent(cur, seed)
        other_tenant = str(uuid4())
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.tenant_id = %s", (other_tenant,))
                cur.execute("SELECT count(*) FROM mcp_remote_execution_intents")
                self.assertEqual(cur.fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
