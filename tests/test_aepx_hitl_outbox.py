import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock
p=pathlib.Path(__file__).resolve().parents[1]/"services/governance/app/hitl_outbox.py"
spec=importlib.util.spec_from_file_location("hitl_outbox",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
TENANT="11111111-1111-4111-8111-111111111111"
EVENT="22222222-2222-4222-8222-222222222222"
def connection():
    db=MagicMock()
    cur=db.cursor.return_value.__enter__.return_value
    return db,cur
class LeaseTests(unittest.TestCase):
    def test_claim_uses_locked_tenant_scope(self):
        db,cur=connection()
        cur.fetchall.return_value=[(EVENT,"topic",{},1)]
        self.assertEqual(len(m.claim(db,tenant_id=TENANT,worker_id="worker")),1)
        sql=" ".join(c.args[0] for c in cur.execute.call_args_list)
        self.assertIn("SKIP LOCKED",sql)
        self.assertIn("app.tenant_id",sql)
        db.commit.assert_called_once()
    def test_claim_invalid_limit(self):
        db,_=connection()
        with self.assertRaises(ValueError):m.claim(db,tenant_id=TENANT,worker_id="w",limit=0)
    def test_claim_failure_rolls_back(self):
        db,cur=connection()
        cur.execute.side_effect=RuntimeError("db failure")
        with self.assertRaises(RuntimeError):m.claim(db,tenant_id=TENANT,worker_id="w")
        db.rollback.assert_called_once()
    def test_settle_requires_live_owned_lease(self):
        db,cur=connection()
        cur.fetchone.return_value=None
        with self.assertRaises(PermissionError):
            m.settle(db,tenant_id=TENANT,event_id=EVENT,worker_id="w",delivered=True)
        db.rollback.assert_called_once()
    def test_settle_success(self):
        db,cur=connection()
        cur.fetchone.return_value=(EVENT,)
        self.assertTrue(m.settle(db,tenant_id=TENANT,event_id=EVENT,worker_id="w",delivered=True))
        db.commit.assert_called_once()
if __name__=="__main__":unittest.main()
