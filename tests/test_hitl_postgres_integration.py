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
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_lifecycle import create_request,decide_request,DecisionConflict
from app.hitl_postgres import consume_with_outbox,ApprovalError
from app.hitl_replay import find_matching_replay

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
