import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_health import outbox_health,HealthQueryDenied

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cur=self.db.cursor.return_value.__enter__.return_value
        self.tenant=uuid4()
    def test_backlog_dead_letter_and_age_alerts(self):
        self.cur.fetchall.return_value=[("pending",101),("dead",2),("delivered",5)]
        self.cur.fetchone.return_value=(400.5,)
        result=outbox_health(self.db,tenant_id=self.tenant)
        self.assertEqual(result["counts"]["pending"],101)
        self.assertEqual(result["alerts"],["pending_backlog","dead_letters","oldest_pending_age"])
        self.assertFalse(result["healthy"])
        self.db.commit.assert_called_once()
    def test_healthy_empty_tenant(self):
        self.cur.fetchall.return_value=[]
        self.cur.fetchone.return_value=(None,)
        result=outbox_health(self.db,tenant_id=self.tenant)
        self.assertTrue(result["healthy"])
        self.assertEqual(result["oldest_pending_seconds"],0)
    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            outbox_health(self.db,tenant_id=self.tenant,warning_dead=-1)
        self.db.cursor.assert_not_called()
    def test_unknown_status_fails_closed(self):
        self.cur.fetchall.return_value=[("unexpected",1)]
        with self.assertRaises(HealthQueryDenied):
            outbox_health(self.db,tenant_id=self.tenant)
        self.db.rollback.assert_called_once()
    def test_db_failure_rolls_back(self):
        self.cur.execute.side_effect=RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            outbox_health(self.db,tenant_id=self.tenant)
        self.db.rollback.assert_called_once()
    def test_query_scoped_to_tenant(self):
        self.cur.fetchall.return_value=[]
        self.cur.fetchone.return_value=(0,)
        outbox_health(self.db,tenant_id=self.tenant)
        calls=self.cur.execute.call_args_list
        self.assertEqual(len(calls),3)
        self.assertTrue(all(str(self.tenant) in str(c.args[1]) for c in calls))
if __name__=="__main__": unittest.main()
