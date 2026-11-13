"""Opt-in PostgreSQL integration tests: DISPOSABLE database only.

Provision an isolated database, apply HITL migrations, create a restricted
non-owner, non-BYPASSRLS application role and grant the needed schema/table
privileges. Set HITL_TEST_DATABASE_URL to that role's connection string.
Never point this suite at production. Tests write durable fixture records.
"""
import os
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_lifecycle import create_request,decide_request,DecisionConflict
from app.hitl_postgres import consume_with_outbox,ApprovalError
from app.hitl_replay import find_matching_replay
from app.hitl_outbox import claim, settle, reap_exhausted, lease_is_current
from app.hitl_recovery import requeue_dead_letter,RecoveryDenied
from app.hitl_execution_receipts import execute_local_once
from app.hitl_health import outbox_health
from app.hitl_remote_reconciliation import reserve_remote,reconcile_remote,ReconciliationRequired

@unittest.skipUnless(os.getenv("HITL_TEST_DATABASE_URL") and os.getenv("HITL_TEST_DISPOSABLE")=="yes",
                     "requires explicit disposable PostgreSQL test DB approval")
class HitlPostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        cls.dsn=os.environ["HITL_TEST_DATABASE_URL"]
        with psycopg.connect(cls.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT current_database(), r.rolsuper, r.rolbypassrls,
                                      r.rolcreatedb, r.rolcreaterole,
                                      d.datdba = r.oid
                               FROM pg_roles r JOIN pg_database d
                                 ON d.datname = current_database()
                               WHERE r.rolname = current_user""")
                database, superuser, bypass, createdb, createrole, owns_db = cur.fetchone()
                expected_db = os.getenv("HITL_TEST_EXPECTED_DATABASE")
                if not expected_db or database != expected_db:
                    raise AssertionError("explicit disposable database name mismatch")
                if superuser or bypass or createdb or createrole or owns_db:
                    raise AssertionError("test role must be restricted and not own database")
                cur.execute("""SELECT EXISTS (
                    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='hitl' AND c.relname='approvals'
                      AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
                )""")
                if cur.fetchone()[0]:
                    raise AssertionError("application role must not own HITL approvals")
    def connect(self):
        return self.psycopg.connect(self.dsn)
    def test_concurrent_decisions_only_one_wins(self):
        tenant=uuid4()
        action={"test_id":str(uuid4()),"operation":"concurrent-decision"}
        with self.connect() as conn:
            approval=create_request(conn,tenant_id=tenant,action=action,
                                    requester_id="requester",
                                    expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        def attempt(actor):
            try:
                with self.connect() as conn:
                    decide_request(conn,tenant_id=tenant,approval_id=approval,
                                   approver_id=actor,decision="approved")
                return "success"
            except DecisionConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,("approver-a","approver-b")))
        self.assertCountEqual(outcomes,["success","conflict"])

    def test_concurrent_consumption_one_outbox_event(self):
        tenant=uuid4()
        action={"test_id":str(uuid4()),"operation":"concurrent-consume"}
        with self.connect() as conn:
            approval=create_request(conn,tenant_id=tenant,action=action,
                                    requester_id="requester",
                                    expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        with self.connect() as conn:
            decide_request(conn,tenant_id=tenant,approval_id=approval,
                           approver_id="approver",decision="approved")
        key="concurrent-"+str(uuid4())
        def attempt(_):
            try:
                with self.connect() as conn:
                    return ("success",consume_with_outbox(
                        conn,tenant_id=tenant,approval_id=approval,action=action,
                        idempotency_key=key,actor_id="worker"))
            except ApprovalError:
                return ("conflict",None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,range(2)))
        self.assertCountEqual([x[0] for x in outcomes],["success","conflict"])
        event=next(x[1] for x in outcomes if x[0]=="success")
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)",(str(tenant),))
                cur.execute("SELECT count(*) FROM hitl.outbox WHERE tenant_id=%s AND idempotency_key=%s",
                            (str(tenant),key))
                self.assertEqual(cur.fetchone()[0],1)
        with self.connect() as conn:
            self.assertEqual(find_matching_replay(
                conn,tenant_id=tenant,approval_id=approval,action=action,
                idempotency_key=key,actor_id="worker"),event)

    def _seed_outbox(self,tenant):
        action={"test_id":str(uuid4()),"operation":"outbox-fault-test"}
        with self.connect() as conn:
            approval=create_request(conn,tenant_id=tenant,action=action,
                                    requester_id="requester",
                                    expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        with self.connect() as conn:
            decide_request(conn,tenant_id=tenant,approval_id=approval,
                           approver_id="approver",decision="approved")
        with self.connect() as conn:
            event=consume_with_outbox(conn,tenant_id=tenant,approval_id=approval,
                                      action=action,idempotency_key="fault-"+str(uuid4()),
                                      actor_id="worker")
        return event

    def _expire_lease(self,tenant,event):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)",(str(tenant),))
                cur.execute("""UPDATE hitl.outbox SET leased_until=now()-interval '1 second'
                               WHERE tenant_id=%s AND id=%s""",(str(tenant),event))

    def test_remote_reconciliation_requires_verified_evidence(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        provider="sandbox-mcp"
        key="reconcile-"+str(uuid4())
        with self.connect() as conn:
            reserve_remote(conn,tenant_id=tenant,event_id=event,
                           provider=provider,idempotency_key=key)
        kwargs=dict(tenant_id=tenant,event_id=event,provider=provider,
                    idempotency_key=key,verified_state="confirmed",
                    evidence_reference="sandbox-confirmation-123",
                    reviewer_id="reviewer-verified",authorized=True)
        with self.connect() as conn:
            with self.assertRaises(ReconciliationRequired):
                reconcile_remote(conn,**kwargs)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("""SELECT state FROM hitl.remote_delivery_receipts
                               WHERE tenant_id=%s AND event_id=%s""",
                            (str(tenant),event))
                self.assertEqual(cur.fetchone()[0],"uncertain")
        with self.connect() as conn:
            result=reconcile_remote(
                conn,**kwargs,
                verify_evidence=lambda **e: (
                    e["tenant_id"]==str(tenant)
                    and e["event_id"]==str(event)
                    and e["idempotency_key"]==key
                    and e["verified_state"]=="confirmed"),
                verify_operator=lambda **o: (
                    o["tenant_id"]==str(tenant) and
                    o["reviewer_id"]=="reviewer-verified" and
                    o["permission"]=="hitl.remote.reconcile"))
        self.assertEqual(result["state"],"confirmed")
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("""SELECT state FROM hitl.remote_delivery_receipts
                               WHERE tenant_id=%s AND event_id=%s""",
                            (str(tenant),event))
                self.assertEqual(cur.fetchone()[0],"confirmed")
                cur.execute("""SELECT count(*) FROM hitl.events
                               WHERE tenant_id=%s AND actor_id=%s
                                 AND event LIKE 'remote_confirmed:%%'""",
                            (str(tenant),"reviewer-verified"))
                self.assertEqual(cur.fetchone()[0],1)
        with self.connect() as conn:
            with self.assertRaises(ReconciliationRequired):
                reconcile_remote(conn,**kwargs,verify_evidence=lambda **e: True,
                                 verify_operator=lambda **o: True)

    def test_concurrent_remote_reservation_only_one_wins(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        key="remote-"+str(uuid4())
        def attempt(_):
            try:
                with self.connect() as conn:
                    reserve_remote(conn,tenant_id=tenant,event_id=event,
                                   provider="sandbox-mcp",idempotency_key=key)
                return "reserved"
            except ReconciliationRequired:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,range(2)))
        self.assertCountEqual(outcomes,["reserved","rejected"])
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("""SELECT state,count(*) FROM hitl.remote_delivery_receipts
                               WHERE tenant_id=%s AND event_id=%s GROUP BY state""",
                            (str(tenant),event))
                self.assertEqual(cur.fetchall(),[("uncertain",1)])

    def test_remote_receipts_not_visible_cross_tenant(self):
        tenant=uuid4()
        other=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            reserve_remote(conn,tenant_id=tenant,event_id=event,
                           provider="sandbox-mcp",idempotency_key="remote-"+str(uuid4()))
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(other),))
                cur.execute("SELECT count(*) FROM hitl.remote_delivery_receipts")
                self.assertEqual(cur.fetchone()[0],0)

    def test_uncertain_remote_delivery_health_alert_is_tenant_scoped(self):
        tenant = uuid4()
        other = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            reserve_remote(conn, tenant_id=tenant, event_id=event,
                           provider="sandbox-mcp",
                           idempotency_key="health-remote-" + str(uuid4()))
        with self.connect() as conn:
            own = outbox_health(conn, tenant_id=tenant)
        with self.connect() as conn:
            other_health = outbox_health(conn, tenant_id=other)
        self.assertEqual(own["uncertain_remote_deliveries"], 1)
        self.assertIn("uncertain_remote_delivery", own["alerts"])
        self.assertFalse(own["healthy"])
        self.assertEqual(other_health["uncertain_remote_deliveries"], 0)
        self.assertNotIn("uncertain_remote_delivery", other_health["alerts"])

    def test_uncertain_remote_age_escalation_is_tenant_scoped(self):
        tenant = uuid4()
        other = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            reserve_remote(conn, tenant_id=tenant, event_id=event,
                           provider="sandbox-mcp",
                           idempotency_key="age-remote-" + str(uuid4()))
        # Alter only a disposable test receipt; never mutate production records.
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("""UPDATE hitl.remote_delivery_receipts
                               SET created_at=now()-interval '600 seconds'
                               WHERE tenant_id=%s AND event_id=%s""",
                            (str(tenant), event))
                self.assertEqual(cur.rowcount, 1)
        with self.connect() as conn:
            own = outbox_health(conn, tenant_id=tenant,
                                warning_uncertain_age_seconds=300)
        with self.connect() as conn:
            other_health = outbox_health(conn, tenant_id=other,
                                         warning_uncertain_age_seconds=300)
        self.assertGreaterEqual(own["oldest_uncertain_remote_seconds"], 300)
        self.assertIn("oldest_uncertain_remote_age", own["alerts"])
        self.assertEqual(other_health["oldest_uncertain_remote_seconds"], 0)
        self.assertNotIn("oldest_uncertain_remote_age", other_health["alerts"])

    def test_outbox_health_is_tenant_isolated(self):
        tenant=uuid4()
        other=uuid4()
        self._seed_outbox(tenant)
        self._seed_outbox(other)
        with self.connect() as conn:
            own=outbox_health(conn,tenant_id=tenant,warning_pending=2)
        with self.connect() as conn:
            other_health=outbox_health(conn,tenant_id=other,warning_pending=2)
        self.assertEqual(own["counts"]["pending"],1)
        self.assertEqual(other_health["counts"]["pending"],1)
        self.assertEqual(own["alerts"],[])
        self.assertEqual(other_health["alerts"],[])

    def test_expired_lease_health_alert_is_tenant_scoped(self):
        tenant = uuid4()
        other = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            rows = claim(conn, tenant_id=tenant, worker_id="health-worker", limit=1)
        self.assertEqual(len(rows), 1)
        self._expire_lease(tenant, event)
        with self.connect() as conn:
            own = outbox_health(conn, tenant_id=tenant)
        with self.connect() as conn:
            other_health = outbox_health(conn, tenant_id=other)
        self.assertEqual(own["expired_leases"], 1)
        self.assertIn("expired_leases", own["alerts"])
        self.assertFalse(own["healthy"])
        self.assertEqual(other_health["expired_leases"], 0)
        self.assertNotIn("expired_leases", other_health["alerts"])

    def test_concurrent_local_receipt_applies_once(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("SELECT payload->>'action_hash' FROM hitl.outbox WHERE id=%s",(event,))
                action_hash=cur.fetchone()[0]
        def attempt(_):
            with self.connect() as conn:
                def local_effect(cur):
                    # A transactional, local effect. No external calls.
                    cur.execute("""INSERT INTO hitl.events
                                   (tenant_id,approval_id,event,actor_id)
                                   SELECT tenant_id,(payload->>'approval_id')::uuid,
                                          'local_receipt_applied','receipt-test'
                                   FROM hitl.outbox WHERE tenant_id=%s AND id=%s""",
                                (str(tenant),event))
                return execute_local_once(
                    conn,tenant_id=tenant,event_id=event,action_hash=action_hash,
                    tool_name="local.receipt-test",apply_local=local_effect,approved=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,range(2)))
        self.assertCountEqual(outcomes,["applied","duplicate"])
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("""SELECT count(*) FROM hitl.events
                               WHERE tenant_id=%s AND event='local_receipt_applied'""",
                            (str(tenant),))
                self.assertEqual(cur.fetchone()[0],1)

    def test_failed_local_effect_rolls_back_and_retry_applies_once(self):
        tenant = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("SELECT payload->>'action_hash' FROM hitl.outbox WHERE id=%s", (event,))
                action_hash = cur.fetchone()[0]

        def local_effect(cur):
            cur.execute("""INSERT INTO hitl.events
                           (tenant_id,approval_id,event,actor_id)
                           SELECT tenant_id,(payload->>'approval_id')::uuid,
                                  'rollback_probe','local-test'
                           FROM hitl.outbox WHERE tenant_id=%s AND id=%s""",
                        (str(tenant), event))

        def failing_effect(cur):
            local_effect(cur)
            raise RuntimeError("simulated worker failure before receipt")

        kwargs = dict(tenant_id=tenant, event_id=event, action_hash=action_hash,
                      tool_name="local.rollback-probe")
        with self.connect() as conn:
            with self.assertRaisesRegex(RuntimeError, "simulated worker failure"):
                execute_local_once(conn, apply_local=failing_effect, **kwargs)

        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("""SELECT count(*) FROM hitl.events
                               WHERE tenant_id=%s AND event='rollback_probe'""", (str(tenant),))
                self.assertEqual(cur.fetchone()[0], 0)
                cur.execute("""SELECT count(*) FROM hitl.execution_receipts
                               WHERE tenant_id=%s AND event_id=%s""", (str(tenant), event))
                self.assertEqual(cur.fetchone()[0], 0)

        with self.connect() as conn:
            self.assertEqual(execute_local_once(conn, apply_local=local_effect, **kwargs),
                             "applied")
        with self.connect() as conn:
            self.assertEqual(execute_local_once(conn, apply_local=local_effect, **kwargs),
                             "duplicate")
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("""SELECT count(*) FROM hitl.events
                               WHERE tenant_id=%s AND event='rollback_probe'""", (str(tenant),))
                self.assertEqual(cur.fetchone()[0], 1)
                cur.execute("""SELECT count(*) FROM hitl.execution_receipts
                               WHERE tenant_id=%s AND event_id=%s""", (str(tenant), event))
                self.assertEqual(cur.fetchone()[0], 1)

    def test_audited_dead_letter_requeue_requires_operator_gate(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            claimed=claim(conn,tenant_id=tenant,worker_id="worker-fail",max_attempts=1)
        with self.connect() as conn:
            settle(conn,tenant_id=tenant,event_id=event,worker_id="worker-fail",
                   attempt_number=claimed[0][3],delivered=False,max_attempts=1)
        kwargs=dict(tenant_id=tenant,event_id=event,operator_id="security-operator",
                    ticket_id="INC-123456",reason="deduplication reviewed before retry")
        with self.connect() as conn:
            with self.assertRaises(RecoveryDenied):
                requeue_dead_letter(conn,**kwargs,approved=False,idempotency_verified=True)
        with self.connect() as conn:
            requeue_dead_letter(conn,**kwargs,approved=True,idempotency_verified=True)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("SELECT status,attempts FROM hitl.outbox WHERE id=%s",(event,))
                self.assertEqual(cur.fetchone(),("pending",0))
                cur.execute("""SELECT count(*) FROM hitl.outbox_recovery_audit
                               WHERE tenant_id=%s AND event_id=%s""",(str(tenant),event))
                self.assertEqual(cur.fetchone()[0],1)
        with self.connect() as conn:
            with self.assertRaises(RecoveryDenied):
                requeue_dead_letter(conn,**kwargs,approved=True,idempotency_verified=True)

    def test_failed_delivery_retry_and_dead_letter_idempotence(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            first=claim(conn,tenant_id=tenant,worker_id="worker-1",max_attempts=2)
        self.assertEqual(len(first),1)
        with self.connect() as conn:
            settle(conn,tenant_id=tenant,event_id=event,worker_id="worker-1",
                   attempt_number=first[0][3],delivered=False,
                   error="redacted delivery failure",retry_seconds=30,max_attempts=2)
        # Move only this disposable test event's retry clock.
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("""UPDATE hitl.outbox SET next_attempt_at=now()-interval '1 second'
                               WHERE id=%s AND tenant_id=%s""",(event,str(tenant)))
        with self.connect() as conn:
            second=claim(conn,tenant_id=tenant,worker_id="worker-2",max_attempts=2)
        self.assertEqual(len(second),1)
        with self.connect() as conn:
            settle(conn,tenant_id=tenant,event_id=event,worker_id="worker-2",
                   attempt_number=second[0][3],delivered=False,
                   error="redacted delivery failure",max_attempts=2)
        with self.connect() as conn:
            self.assertEqual(reap_exhausted(conn,tenant_id=tenant,max_attempts=2),[])
            self.assertEqual(claim(conn,tenant_id=tenant,worker_id="worker-3",
                                   max_attempts=2),[])
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)",(str(tenant),))
                cur.execute("SELECT status,attempts FROM hitl.outbox WHERE id=%s",(event,))
                self.assertEqual(cur.fetchone(),("dead",2))

    def test_rls_requires_tenant_context_and_restricted_role(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT rolsuper,rolbypassrls FROM pg_roles
                               WHERE rolname=current_user""")
                self.assertEqual(cur.fetchone(),(False,False))
                cur.execute("""SELECT has_table_privilege(current_user,'hitl.outbox','DELETE'),
                                      has_table_privilege(current_user,'hitl.approvals','TRUNCATE')""")
                self.assertEqual(cur.fetchone(),(False,False))
                # With no app.tenant_id, FORCE RLS must deny visibility.
                cur.execute("SELECT count(*) FROM hitl.outbox WHERE id=%s",(event,))
                self.assertEqual(cur.fetchone()[0],0)
                cur.execute("SELECT set_config('app.tenant_id', %s, true)",(str(uuid4()),))
                cur.execute("SELECT count(*) FROM hitl.outbox WHERE id=%s",(event,))
                self.assertEqual(cur.fetchone()[0],0)
                cur.execute("SELECT set_config('app.tenant_id', %s, true)",(str(tenant),))
                cur.execute("SELECT count(*) FROM hitl.outbox WHERE id=%s",(event,))
                self.assertEqual(cur.fetchone()[0],1)

    def test_cross_tenant_outbox_update_is_blocked_by_rls(self):
        tenant = uuid4()
        other = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(other),))
                cur.execute("""UPDATE hitl.outbox SET status='dead'
                               WHERE tenant_id=%s AND id=%s""", (str(tenant), event))
                self.assertEqual(cur.rowcount, 0)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("SELECT status FROM hitl.outbox WHERE tenant_id=%s AND id=%s",
                            (str(tenant), event))
                self.assertEqual(cur.fetchone()[0], "pending")

    def test_cross_tenant_outbox_delete_is_not_granted(self):
        tenant = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT has_table_privilege(current_user,
                               'hitl.outbox', 'DELETE')""")
                self.assertIs(cur.fetchone()[0], False)
                cur.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant),))
                cur.execute("SELECT count(*) FROM hitl.outbox WHERE tenant_id=%s AND id=%s",
                            (str(tenant), event))
                self.assertEqual(cur.fetchone()[0], 1)

    def test_multi_worker_claim_and_stale_settlement(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        def worker(worker_id):
            with self.connect() as conn:
                return claim(conn,tenant_id=tenant,worker_id=worker_id,limit=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,("worker-a","worker-b")))
        self.assertEqual(sum(len(rows) for rows in results),1)
        winning=next((name,rows[0]) for name,rows in zip(("worker-a","worker-b"),results) if rows)
        self.assertEqual(str(winning[1][0]),event)
        self._expire_lease(tenant,event)
        with self.connect() as conn:
            replacement=claim(conn,tenant_id=tenant,worker_id="worker-new",limit=1)
        self.assertEqual(len(replacement),1)
        with self.connect() as conn:
            with self.assertRaises(PermissionError):
                settle(conn,tenant_id=tenant,event_id=event,worker_id=winning[0],
                       attempt_number=winning[1][3],delivered=True)
        with self.connect() as conn:
            settle(conn,tenant_id=tenant,event_id=event,worker_id="worker-new",
                   attempt_number=replacement[0][3],delivered=True)

    def test_lease_preflight_rejects_expired_and_reassigned_worker(self):
        tenant = uuid4()
        event = self._seed_outbox(tenant)
        with self.connect() as conn:
            first = claim(conn, tenant_id=tenant, worker_id="worker-old", limit=1)
        self.assertEqual(len(first), 1)
        first_attempt = first[0][3]
        with self.connect() as conn:
            self.assertTrue(lease_is_current(
                conn, tenant_id=tenant, event_id=event,
                worker_id="worker-old", attempt_number=first_attempt))
        self._expire_lease(tenant, event)
        with self.connect() as conn:
            self.assertFalse(lease_is_current(
                conn, tenant_id=tenant, event_id=event,
                worker_id="worker-old", attempt_number=first_attempt))
        with self.connect() as conn:
            second = claim(conn, tenant_id=tenant, worker_id="worker-new", limit=1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0][3], first_attempt + 1)
        with self.connect() as conn:
            self.assertFalse(lease_is_current(
                conn, tenant_id=tenant, event_id=event,
                worker_id="worker-old", attempt_number=first_attempt))
            self.assertTrue(lease_is_current(
                conn, tenant_id=tenant, event_id=event,
                worker_id="worker-new", attempt_number=second[0][3]))
        with self.connect() as conn:
            with self.assertRaises(PermissionError):
                settle(conn, tenant_id=tenant, event_id=event,
                       worker_id="worker-old", attempt_number=first_attempt,
                       delivered=True)
        with self.connect() as conn:
            settle(conn, tenant_id=tenant, event_id=event,
                   worker_id="worker-new", attempt_number=second[0][3],
                   delivered=True)

    def test_exhausted_crashed_lease_is_dead_lettered(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            rows=claim(conn,tenant_id=tenant,worker_id="crashing-worker",limit=1,max_attempts=1)
        self.assertEqual(len(rows),1)
        self._expire_lease(tenant,event)
        with self.connect() as conn:
            dead=reap_exhausted(conn,tenant_id=tenant,max_attempts=1)
        self.assertIn(str(event),[str(x) for x in dead])
        with self.connect() as conn:
            self.assertEqual(claim(conn,tenant_id=tenant,worker_id="new-worker",
                                   limit=1,max_attempts=1),[])

    def test_crash_after_delivery_requires_adapter_deduplication(self):
        tenant=uuid4()
        event=self._seed_outbox(tenant)
        with self.connect() as conn:
            first=claim(conn,tenant_id=tenant,worker_id="worker-a",limit=1)
        self.assertEqual(len(first),1)
        # Simulate an external adapter success followed by process crash
        # BEFORE settle: database cannot know that the side effect occurred.
        self._expire_lease(tenant,event)
        with self.connect() as conn:
            retry=claim(conn,tenant_id=tenant,worker_id="worker-b",limit=1)
        self.assertEqual(str(retry[0][0]),event)
        self.assertEqual(retry[0][3],first[0][3]+1)
        with self.connect() as conn:
            settle(conn,tenant_id=tenant,event_id=event,worker_id="worker-b",
                   attempt_number=retry[0][3],delivered=True)

    def test_tenant_isolation_and_lifecycle(self):
        tenant_a,tenant_b=uuid4(),uuid4()
        action={"test_id":str(uuid4()),"operation":"no-external-side-effect"}
        with self.connect() as conn:
            approval=create_request(conn,tenant_id=tenant_a,action=action,requester_id="requester",
                                    expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        with self.connect() as conn:
            with self.assertRaises(DecisionConflict):
                decide_request(conn,tenant_id=tenant_b,approval_id=approval,
                               approver_id="approver",decision="approved")
        with self.connect() as conn:
            with self.assertRaises(DecisionConflict):
                decide_request(conn,tenant_id=tenant_a,approval_id=approval,
                               approver_id="requester",decision="approved")
        with self.connect() as conn:
            self.assertEqual(decide_request(conn,tenant_id=tenant_a,approval_id=approval,
                                            approver_id="approver",decision="approved"),"approved")
        key="integration-"+str(uuid4())
        with self.connect() as conn:
            with self.assertRaises(ApprovalError):
                consume_with_outbox(conn,tenant_id=tenant_b,approval_id=approval,
                                    action=action,idempotency_key=key,actor_id="worker")
        with self.connect() as conn:
            event=consume_with_outbox(conn,tenant_id=tenant_a,approval_id=approval,
                                      action=action,idempotency_key=key,actor_id="worker")
        with self.connect() as conn:
            self.assertEqual(find_matching_replay(conn,tenant_id=tenant_a,approval_id=approval,
                                                   action=action,idempotency_key=key,actor_id="worker"),event)
        with self.connect() as conn:
            self.assertIsNone(find_matching_replay(conn,tenant_id=tenant_b,approval_id=approval,
                                                    action=action,idempotency_key=key,actor_id="worker"))
        with self.connect() as conn:
            with self.assertRaises(ApprovalError):
                consume_with_outbox(conn,tenant_id=tenant_a,approval_id=approval,
                                    action=action,idempotency_key=key,actor_id="worker")
if __name__=="__main__":unittest.main()
