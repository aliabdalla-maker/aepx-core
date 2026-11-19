"""Fail-closed bounded identity snapshot validation regression."""
import itertools
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_snapshot import publish_identity_snapshot,SnapshotRejected

class BoundedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.connection=MagicMock()
        self.args=dict(connection=self.connection,tenant_id=str(uuid4()),
            issuer="https://identity.example",memberships=["member-12345"],
            revoked_tokens=[],captured_at=datetime.now(timezone.utc),revision=1)
    def test_unbounded_member_generator_is_rejected(self):
        self.args["memberships"]=itertools.repeat("member-12345")
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.connection.cursor.assert_not_called()
        self.connection.rollback.assert_called_once()
    def test_unbounded_revocation_generator_is_rejected(self):
        self.args["revoked_tokens"]=itertools.repeat(("member-12345","token-12345"))
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.connection.cursor.assert_not_called()
    def test_credentials_in_issuer_denied(self):
        self.args["issuer"]="https://user:pass@identity.example"
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.connection.cursor.assert_not_called()
    def test_issuer_query_denied(self):
        self.args["issuer"]="https://identity.example/?token=secret"
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.connection.cursor.assert_not_called()
    def test_non_https_issuer_denied(self):
        self.args["issuer"]="http://identity.example"
        with self.assertRaises(SnapshotRejected):
            publish_identity_snapshot(**self.args)
        self.connection.cursor.assert_not_called()
if __name__=="__main__":
    unittest.main()
