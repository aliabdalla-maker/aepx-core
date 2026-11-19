import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock

path=pathlib.Path(__file__).resolve().parents[1]/"services/governance/app/hitl_postgres.py"
spec=importlib.util.spec_from_file_location("hitl_postgres",path)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TENANT="11111111-1111-4111-8111-111111111111"
APPROVAL="22222222-2222-4222-8222-222222222222"
ACTION={"tool":"erp.update","record":"invoice:7"}

def fake_connection(row):
    conn=MagicMock()
    cursor=conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=row
    cursor.rowcount=1
    return conn,cursor

class TransactionTests(unittest.TestCase):
    def test_success_commits_outbox_in_same_transaction(self):
        conn,cur=fake_connection((mod.fingerprint(ACTION),"approved",True,"reviewer"))
        event=mod.consume_with_outbox(conn,tenant_id=TENANT,approval_id=APPROVAL,
                                      action=ACTION,idempotency_key="key-1",actor_id="executor")
        self.assertTrue(event)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        statements=[call.args[0] for call in cur.execute.call_args_list]
        self.assertTrue(any("set_config('app.tenant_id'" in s for s in statements))
        self.assertTrue(any("FOR UPDATE" in s for s in statements))
        self.assertTrue(any("INSERT INTO hitl.outbox" in s for s in statements))
    def test_pending_denied_and_rolled_back(self):
        conn,_=fake_connection((mod.fingerprint(ACTION),"pending",True,None))
        with self.assertRaises(mod.ApprovalError):
            mod.consume_with_outbox(conn,tenant_id=TENANT,approval_id=APPROVAL,
                                    action=ACTION,idempotency_key="key-2",actor_id="executor")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
    def test_expired_denied(self):
        conn,_=fake_connection((mod.fingerprint(ACTION),"approved",False,"reviewer"))
        with self.assertRaises(mod.ApprovalError):
            mod.consume_with_outbox(conn,tenant_id=TENANT,approval_id=APPROVAL,
                                    action=ACTION,idempotency_key="key-3",actor_id="executor")
    def test_action_mismatch_denied(self):
        conn,_=fake_connection(("0"*64,"approved",True,"reviewer"))
        with self.assertRaises(mod.ApprovalError):
            mod.consume_with_outbox(conn,tenant_id=TENANT,approval_id=APPROVAL,
                                    action=ACTION,idempotency_key="key-4",actor_id="executor")
    def test_invalid_tenant_rolls_back(self):
        conn,_=fake_connection((mod.fingerprint(ACTION),"approved",True,"reviewer"))
        with self.assertRaises(ValueError):
            mod.consume_with_outbox(conn,tenant_id="invalid",approval_id=APPROVAL,
                                    action=ACTION,idempotency_key="key-5",actor_id="executor")
        conn.rollback.assert_not_called()
    def test_insert_failure_rolls_back(self):
        conn,cur=fake_connection((mod.fingerprint(ACTION),"approved",True,"reviewer"))
        def fail_outbox(sql,*args):
            if "INSERT INTO hitl.outbox" in sql:raise RuntimeError("outbox unavailable")
        cur.execute.side_effect=fail_outbox
        with self.assertRaises(RuntimeError):
            mod.consume_with_outbox(conn,tenant_id=TENANT,approval_id=APPROVAL,
                                    action=ACTION,idempotency_key="key-6",actor_id="executor")
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
if __name__=="__main__":unittest.main()
