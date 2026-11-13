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
from app.mcp_remote_tenant_context import bind_verified_tenant, UnsafeTenantContext
from app.mcp_remote_intent_transition import transition_intent, TransitionDenied
from app.mcp_remote_intent_state import IntentState
from app.mcp_remote_dispatch_claim import claim_dispatch, DispatchClaimDenied
from app.mcp_remote_reconciliation import mark_stale_dispatch_uncertain, ReconciliationDenied
from app.mcp_remote_dispatch_commit_gate import verify_committed_intent, DispatchNotCommitted

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
                cur.execute("SELECT current_database(), current_user, inet_server_addr()")
                db_name, db_role, server_ip = cur.fetchone()
                if db_name != "aepx_acceptance" or db_role != "aepx_test":
                    raise RuntimeError("refusing destructive test setup outside disposable aepx_acceptance/aepx_test")
                if server_ip is not None and str(server_ip) not in ("127.0.0.1", "::1"):
                    raise RuntimeError("refusing non-loopback PostgreSQL acceptance database")
                cur.execute(DDL)
                cur.execute("GRANT USAGE ON SCHEMA public TO aepx_runtime")
                cur.execute("GRANT SELECT, INSERT, UPDATE ON mcp_remote_execution_intents TO aepx_runtime")

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, inet_server_addr()")
                db_name, db_role, server_ip = cur.fetchone()
                if db_name != "aepx_acceptance" or db_role != "aepx_test":
                    raise RuntimeError("refusing destructive cleanup outside disposable acceptance database")
                if server_ip is not None and str(server_ip) not in ("127.0.0.1", "::1"):
                    raise RuntimeError("refusing non-loopback acceptance cleanup")
                cur.execute("DROP TABLE IF EXISTS mcp_remote_execution_intents")

    def _reserve(self, intent, results, errors, barrier=None):
        try:
            with psycopg.connect(RUNTIME_DSN) as conn:
                with conn.cursor() as cur:
                    bind_verified_tenant(cur, verified_tenant_id=intent.tenant_id, expected_runtime_role="aepx_runtime")
                    if barrier is not None:
                        barrier.wait(timeout=10)
                    results.append(reserve_intent(cur, intent))
        except Exception as exc:
            errors.append(exc)

    def test_tenant_binding_does_not_leak_after_commit(self):
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                self.assertEqual(cur.fetchone()[0], self.tenant)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                self.assertNotEqual(cur.fetchone()[0], self.tenant)

    def test_tenant_binding_does_not_leak_after_rollback(self):
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                self.assertEqual(cur.fetchone()[0], self.tenant)
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                self.assertNotEqual(cur.fetchone()[0], self.tenant)

    def test_dispatch_gate_requires_committed_reservation(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="8"*64,
            idempotency_key="commit-gate-0001")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
                with psycopg.connect(RUNTIME_DSN) as reader:
                    with reader.cursor() as read_cur:
                        bind_verified_tenant(read_cur, verified_tenant_id=self.tenant,
                                             expected_runtime_role="aepx_runtime")
                        with self.assertRaises(DispatchNotCommitted):
                            verify_committed_intent(read_cur, tenant_id=self.tenant,
                                request_id=candidate.request_id,
                                idempotency_key=candidate.idempotency_key)
            writer.commit()
        with psycopg.connect(RUNTIME_DSN) as reader:
            with reader.cursor() as read_cur:
                bind_verified_tenant(read_cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                verified = verify_committed_intent(read_cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
                self.assertEqual(verified.request_id, candidate.request_id)

    def test_dispatch_claim_has_single_database_winner(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="7"*64,
            idempotency_key="claim-pg-000001")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        with psycopg.connect(RUNTIME_DSN) as first:
            with first.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            first.commit()
        with psycopg.connect(RUNTIME_DSN) as second:
            with second.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                with self.assertRaises(DispatchClaimDenied):
                    claim_dispatch(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id,
                        idempotency_key=candidate.idempotency_key)

    def test_simultaneous_dispatch_claims_exactly_one_winner(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="6"*64,
            idempotency_key="claim-race-00001")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        barrier = threading.Barrier(2)
        outcomes, errors = [], []
        lock = threading.Lock()
        def worker():
            try:
                with psycopg.connect(RUNTIME_DSN) as conn:
                    with conn.cursor() as cur:
                        bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                             expected_runtime_role="aepx_runtime")
                        barrier.wait(timeout=10)
                        try:
                            claim_dispatch(cur, tenant_id=self.tenant,
                                request_id=candidate.request_id,
                                idempotency_key=candidate.idempotency_key)
                            outcome = "claimed"
                        except DispatchClaimDenied:
                            outcome = "denied"
                    conn.commit()
                with lock:
                    outcomes.append(outcome)
            except Exception as exc:
                with lock:
                    errors.append(exc)
        workers = [threading.Thread(target=worker) for _ in range(2)]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in workers), "claim worker hung")
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(outcomes, ["claimed", "denied"])
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (candidate.request_id,))
                self.assertEqual(cur.fetchone()[0], "dispatched")

    def test_rolled_back_dispatch_claim_remains_reservable(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="5"*64,
            idempotency_key="claim-rollback-001")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        with psycopg.connect(RUNTIME_DSN) as abandoned:
            with abandoned.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            abandoned.rollback()
        with psycopg.connect(RUNTIME_DSN) as recovery:
            with recovery.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (candidate.request_id,))
                self.assertEqual(cur.fetchone()[0], "reserved")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            recovery.commit()
        with psycopg.connect(RUNTIME_DSN) as verify:
            with verify.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (candidate.request_id,))
                self.assertEqual(cur.fetchone()[0], "dispatched")

    def test_committed_claim_cannot_be_replayed_after_restart(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="4"*64,
            idempotency_key="claim-restart-001")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        with psycopg.connect(RUNTIME_DSN) as first:
            with first.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            first.commit()
        with psycopg.connect(RUNTIME_DSN) as restarted:
            with restarted.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                with self.assertRaises(DispatchClaimDenied):
                    claim_dispatch(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id,
                        idempotency_key=candidate.idempotency_key)

    def test_abrupt_connection_close_discards_uncommitted_claim(self):
        """Simulate worker disappearance without commit or explicit rollback."""
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="3"*64,
            idempotency_key="claim-disconnect-01")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        abandoned = psycopg.connect(RUNTIME_DSN)
        try:
            with abandoned.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
        finally:
            abandoned.close()
        with psycopg.connect(RUNTIME_DSN) as recovery:
            with recovery.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (candidate.request_id,))
                self.assertEqual(cur.fetchone()[0], "reserved")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            recovery.commit()

    def test_runtime_role_cannot_bypass_rls(self):
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                    "FROM pg_catalog.pg_roles WHERE rolname = current_user"
                )
                role = cur.fetchone()
                self.assertIsNotNone(role)
                self.assertEqual(role[0], "aepx_runtime")
                self.assertEqual(tuple(role[1:]), (False, False, False, False))

    def test_table_forces_rls_and_policy_is_tenant_scoped(self):
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_catalog.pg_class "
                    "WHERE oid = 'public.mcp_remote_execution_intents'::regclass"
                )
                self.assertEqual(cur.fetchone(), (True, True))
                cur.execute(
                    "SELECT policyname, cmd, qual, with_check "
                    "FROM pg_catalog.pg_policies "
                    "WHERE schemaname = 'public' "
                    "AND tablename = 'mcp_remote_execution_intents'"
                )
                policies = cur.fetchall()
                self.assertEqual(len(policies), 1)
                name, command, using, check = policies[0]
                self.assertEqual(name, "mcp_remote_intent_tenant")
                self.assertEqual(command, "ALL")
                self.assertIn("app.tenant_id", using)
                self.assertIn("app.tenant_id", check)

    def test_committed_claim_survives_abrupt_connection_close(self):
        """Committed dispatch claim remains non-replayable after worker disconnect."""
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="2"*64,
            idempotency_key="claim-after-close01")
        with psycopg.connect(RUNTIME_DSN) as writer:
            with writer.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            writer.commit()
        worker = psycopg.connect(RUNTIME_DSN)
        try:
            with worker.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id,
                    idempotency_key=candidate.idempotency_key)
            worker.commit()
        finally:
            worker.close()
        with psycopg.connect(RUNTIME_DSN) as restarted:
            with restarted.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (candidate.request_id,))
                self.assertEqual(cur.fetchone()[0], "dispatched")
                with self.assertRaises(DispatchClaimDenied):
                    claim_dispatch(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id,
                        idempotency_key=candidate.idempotency_key)

    def test_wrong_runtime_role_fails_closed(self):
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                with self.assertRaises(UnsafeTenantContext):
                    bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                         expected_runtime_role="unexpected_role")

    def test_two_workers_single_reservation(self):
        results, errors = [], []
        from dataclasses import replace
        concurrent_intent = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()), idempotency_key="race-00000001")
        barrier = threading.Barrier(2)
        workers = [threading.Thread(target=self._reserve, args=(concurrent_intent,results,errors,barrier))
                   for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=15)
        self.assertFalse(any(worker.is_alive() for worker in workers), "worker hung")
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(results, ["created", "existing"])
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
                cur.execute("SELECT count(*) FROM mcp_remote_execution_intents WHERE request_id = %s",
                            (concurrent_intent.request_id,))
                self.assertEqual(cur.fetchone()[0], 1)

    def test_same_key_different_request_is_denied(self):
        from dataclasses import replace
        from app.mcp_remote_intent_reservation import ReservationDenied
        first = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
                        idempotency_key="collision-000001", action_hash="e"*64)
        second = replace(first, request_id=str(uuid4()), approval_id=str(uuid4()),
                         action_hash="f"*64)
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, first), "created")
                with self.assertRaises(ReservationDenied):
                    reserve_intent(cur, second)

    def test_conflicting_request_key_rejected(self):
        from dataclasses import replace
        from app.mcp_remote_intent_reservation import ReservationDenied
        conflicting = replace(self.intent, tool_name="tool.delete")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
                reserve_intent(cur, self.intent)
                with self.assertRaises(ReservationDenied):
                    reserve_intent(cur, conflicting)

    def test_atomic_transition_rejects_stale_and_cross_tenant(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()),
            approval_id=str(uuid4()), action_hash="9"*64,
            idempotency_key="transition-000001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
                self.assertEqual(transition_intent(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id, current=IntentState.RESERVED,
                    target=IntentState.DISPATCHED), IntentState.DISPATCHED)
                with self.assertRaises(TransitionDenied):
                    transition_intent(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id, current=IntentState.RESERVED,
                        target=IntentState.DISPATCHED)
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=str(uuid4()), expected_runtime_role="aepx_runtime")
                with self.assertRaises(TransitionDenied):
                    transition_intent(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id, current=IntentState.DISPATCHED,
                        target=IntentState.UNCERTAIN)

    def test_stale_dispatch_quarantined_once(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
            action_hash="5"*64, idempotency_key="reconcile-pg-0001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant, request_id=candidate.request_id,
                               idempotency_key=candidate.idempotency_key)
            conn.commit()
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE mcp_remote_execution_intents SET updated_at = now() - interval '120 seconds' WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id, minimum_age_seconds=60), "uncertain")
                with self.assertRaises(ReconciliationDenied):
                    mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id, minimum_age_seconds=60)
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
                self.assertEqual(cur.fetchone()[0], "uncertain")

    def test_simultaneous_reconciliation_has_one_winner(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
            action_hash="3"*64, idempotency_key="reconcile-race-01")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(reserve_intent(cur, candidate), "created")
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant, request_id=candidate.request_id,
                               idempotency_key=candidate.idempotency_key)
            conn.commit()
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE mcp_remote_execution_intents SET updated_at = now() - interval '120 seconds' WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
        barrier = threading.Barrier(2)
        outcomes, errors = [], []
        lock = threading.Lock()
        def worker():
            try:
                with psycopg.connect(RUNTIME_DSN) as conn:
                    with conn.cursor() as cur:
                        bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                             expected_runtime_role="aepx_runtime")
                        barrier.wait(timeout=10)
                        try:
                            result = mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                                request_id=candidate.request_id, minimum_age_seconds=60)
                        except ReconciliationDenied:
                            result = "denied"
                        with lock:
                            outcomes.append(result)
            except Exception as exc:
                with lock:
                    errors.append(exc)
        workers = [threading.Thread(target=worker) for _ in range(2)]
        for worker_thread in workers:
            worker_thread.start()
        for worker_thread in workers:
            worker_thread.join(timeout=15)
        self.assertFalse(any(worker_thread.is_alive() for worker_thread in workers), "worker hung")
        self.assertFalse(errors, str(errors))
        self.assertCountEqual(outcomes, ["uncertain", "denied"])
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
                self.assertEqual(cur.fetchone()[0], "uncertain")

    def test_reconciliation_cross_tenant_isolation(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
                            action_hash="2"*64, idempotency_key="reconcile-isolation-01")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                reserve_intent(cur, candidate)
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant, request_id=candidate.request_id,
                               idempotency_key=candidate.idempotency_key)
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=str(uuid4()),
                                     expected_runtime_role="aepx_runtime")
                with self.assertRaises(ReconciliationDenied):
                    mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id, minimum_age_seconds=1)

    def test_reconciliation_transaction_rollback(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
                            action_hash="1"*64, idempotency_key="reconcile-rollback-01")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                reserve_intent(cur, candidate)
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant, request_id=candidate.request_id,
                               idempotency_key=candidate.idempotency_key)
            conn.commit()
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE mcp_remote_execution_intents SET updated_at = now() - interval '120 seconds' WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                self.assertEqual(mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                    request_id=candidate.request_id, minimum_age_seconds=60), "uncertain")
            conn.rollback()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                cur.execute("SELECT state FROM mcp_remote_execution_intents WHERE tenant_id = %s AND request_id = %s",
                            (self.tenant, candidate.request_id))
                self.assertEqual(cur.fetchone()[0], "dispatched")

    def test_recent_dispatch_not_quarantined(self):
        from dataclasses import replace
        candidate = replace(self.intent, request_id=str(uuid4()), approval_id=str(uuid4()),
            action_hash="4"*64, idempotency_key="reconcile-fresh-01")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                reserve_intent(cur, candidate)
            conn.commit()
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=self.tenant,
                                     expected_runtime_role="aepx_runtime")
                claim_dispatch(cur, tenant_id=self.tenant, request_id=candidate.request_id,
                               idempotency_key=candidate.idempotency_key)
                with self.assertRaises(ReconciliationDenied):
                    mark_stale_dispatch_uncertain(cur, tenant_id=self.tenant,
                        request_id=candidate.request_id, minimum_age_seconds=3600)

    def test_cross_tenant_write_rejected(self):
        other_tenant = str(uuid4())
        candidate = IntentReservation(self.tenant, str(uuid4()), str(uuid4()),
            "b"*64, "resource-other", "tool.read", "2025-11-25", "cross-tenant-0001")
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=other_tenant, expected_runtime_role="aepx_runtime")
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
                bind_verified_tenant(cur, verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
                reserve_intent(cur, seed)
        other_tenant = str(uuid4())
        with psycopg.connect(RUNTIME_DSN) as conn:
            with conn.cursor() as cur:
                bind_verified_tenant(cur, verified_tenant_id=other_tenant, expected_runtime_role="aepx_runtime")
                cur.execute("SELECT count(*) FROM mcp_remote_execution_intents")
                self.assertEqual(cur.fetchone()[0], 0)

if __name__ == "__main__":
    unittest.main()
