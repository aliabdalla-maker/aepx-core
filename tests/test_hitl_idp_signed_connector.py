import hashlib
import hmac
import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import MagicMock,patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_idp_signed_connector import publish_signed_idp_snapshot,validate_pinned_snapshot_url
from app.hitl_identity_snapshot import SnapshotRejected

class SignedIdpConnectorTests(unittest.TestCase):
    def setUp(self):
        self.secret=b"x"*32
        self.tenant=str(uuid4())
        self.issuer="https://id.example"
        self.payload=json.dumps(dict(tenant_id=self.tenant,issuer=self.issuer,
            memberships=["subject-123"],revoked_tokens=[],
            captured_at=datetime.now(timezone.utc).isoformat(),revision=1)).encode()
        self.signature=hmac.new(self.secret,self.payload,hashlib.sha256).hexdigest()
        self.args=dict(connection=MagicMock(),payload=self.payload,signature=self.signature,
            secret=self.secret,expected_tenant=self.tenant,expected_issuer=self.issuer)
    @patch("app.hitl_idp_signed_connector.publish_identity_snapshot",return_value=True)
    def test_signed_snapshot_published(self,publisher):
        self.assertTrue(publish_signed_idp_snapshot(**self.args))
        publisher.assert_called_once()
    def test_tampered_payload_denied(self):
        self.args["payload"]=self.payload+b" "
        with self.assertRaises(SnapshotRejected):
            publish_signed_idp_snapshot(**self.args)
    def test_wrong_tenant_denied(self):
        self.args["expected_tenant"]=str(uuid4())
        with self.assertRaises(SnapshotRejected):
            publish_signed_idp_snapshot(**self.args)
    def test_wrong_issuer_denied(self):
        self.args["expected_issuer"]="https://other.example"
        with self.assertRaises(SnapshotRejected):
            publish_signed_idp_snapshot(**self.args)
    def test_short_secret_denied(self):
        self.args["secret"]=b"short"
        with self.assertRaises(SnapshotRejected):
            publish_signed_idp_snapshot(**self.args)
    def test_oversize_denied(self):
        self.args["max_bytes"]=10
        with self.assertRaises(SnapshotRejected):
            publish_signed_idp_snapshot(**self.args)
    def test_pinned_https_url(self):
        self.assertEqual(validate_pinned_snapshot_url("https://id.example/snapshots",
                         expected_host="id.example"),"https://id.example/snapshots")
        for url in ("http://id.example/x","https://evil.example/x",
                    "https://user@id.example/x","https://id.example:444/x"):
            with self.subTest(url=url),self.assertRaises(SnapshotRejected):
                validate_pinned_snapshot_url(url,expected_host="id.example")
if __name__=="__main__":
    unittest.main()
