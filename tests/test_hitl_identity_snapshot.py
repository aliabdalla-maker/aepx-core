import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_snapshot import publish_identity_snapshot,SnapshotRejected

class IdentitySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.conn=MagicMock()
        self.cur=self.conn.cursor.return_value.__enter__.return_value
        self.args=dict(connection=self.conn,tenant_id=str(uuid4()),
            issuer="https://identity.example",memberships=["operator-123"],
            revoked_tokens=[("operator-123","token-123456")],
            captured_at=datetime.now(timezone.utc))
    def test_atomic_snapshot_committed(self):
        self.assertTrue(publish_identity_snapshot(**self.args))
        self.conn.commit.assert_called_once()
        self.assertEqual(self.cur.execute.call_count,8)
        self.assertIn("healthy=true",self.cur.execute.call_args.args[0])
    def test_stale_snapshot_denied_before_writes(self):
        self.args["captured_at"]-=timedelta(minutes=2)
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.cur.execute.assert_not_called()
        self.conn.rollback.assert_called_once()
    def test_future_snapshot_denied(self):
        self.args["captured_at"]+=timedelta(minutes=1)
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
    def test_duplicate_member_denied(self):
        self.args["memberships"]=["operator-123","operator-123"]
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
    def test_duplicate_revocation_denied(self):
        self.args["revoked_tokens"]=[("operator-123","token-123456")]*2
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
    def test_sql_failure_rolls_back(self):
        self.cur.execute.side_effect=RuntimeError("DB offline")
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()
    def test_invalid_subject_denied(self):
        self.args["memberships"]=["short"]
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
if __name__=="__main__":
    unittest.main()
