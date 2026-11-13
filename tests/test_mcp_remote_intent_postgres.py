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
try:
    import psycopg
except ImportError:
    psycopg = None

@unittest.skipUnless(DSN and psycopg, "disposable PostgreSQL DSN and psycopg required")
class PostgresReservationAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tenant = str(uuid4())
        cls.intent = IntentReservation(cls.tenant, str(uuid4()), str(uuid4()),
            "a"*64, "approved-resource", "tool.read", "2025-11-25", "request-000001")
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(DDL)

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS mcp_remote_execution_intents")

    def _reserve(self, intent, results, errors):
        try:
            with psycopg.connect(DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.tenant_id = %s", (intent.tenant_id,))
                    results.append(reserve_intent(cur, intent))
        except Exception as exc:
            errors.append(exc)

    def test_two_workers_single_reservation(self):
        results, errors = [], []
        workers = [threading.Thread(target=self._reserve, args=(self.intent,results,errors))
                   for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=15)
        self.assertFalse(any(worker.is_alive() for worker in workers), "worker hung")
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(results, ["created", "existing"])

    def test_cross_tenant_read_denied(self):
        other_tenant = str(uuid4())
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.tenant_id = %s", (other_tenant,))
                cur.execute("SELECT count(*) FROM mcp_remote_execution_intents")
                self.assertEqual(cur.fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
