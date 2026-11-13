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
from app.hitl_outbox import claim, settle, reap_exhausted

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
                cur.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                superuser,bypass=cur.fetchone()
                if superuser or bypass:
                    raise AssertionError("test application role must not bypass RLS")
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
