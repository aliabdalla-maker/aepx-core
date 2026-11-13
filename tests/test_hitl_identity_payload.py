import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import MagicMock,patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_payload import parse_snapshot_payload,publish_bounded_snapshot
from app.hitl_identity_snapshot import SnapshotRejected

class PayloadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.payload=dict(tenant_id=str(uuid4()),issuer="https://id.example",
            memberships=["subject-123"],revoked_tokens=[],
            captured_at=datetime.now(timezone.utc).isoformat(),revision=1)
    def encoded(self):
        return json.dumps(self.payload).encode()
    def test_valid_complete_snapshot(self):
        self.assertEqual(parse_snapshot_payload(self.encoded())["revision"],1)
    def test_reject_over_byte_limit(self):
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(self.encoded(),max_bytes=16)
    def test_reject_duplicate_json_keys(self):
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(b'{"tenant_id":"a","tenant_id":"b"}')
    def test_reject_unknown_field(self):
        self.payload["unexpected"]="value"
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(self.encoded())
    def test_reject_delta_instead_of_complete_snapshot(self):
        del self.payload["revoked_tokens"]
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(self.encoded())
    def test_reject_boolean_revision(self):
        self.payload["revision"]=True
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(self.encoded())
    def test_reject_non_bytes(self):
        with self.assertRaises(SnapshotRejected):
            parse_snapshot_payload(self.encoded().decode())
    @patch("app.hitl_identity_payload.publish_identity_snapshot",return_value=True)
    def test_forward_only_parsed_fields(self,publisher):
        self.assertTrue(publish_bounded_snapshot(MagicMock(),payload=self.encoded()))
        self.assertEqual(publisher.call_args.kwargs["revision"],1)
if __name__=="__main__":
    unittest.main()
