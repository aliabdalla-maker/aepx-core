import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_idp_transport import SnapshotResponse,ingest_trusted_idp_snapshot
from app.hitl_identity_snapshot import SnapshotRejected

class IdpTransportTests(unittest.TestCase):
    def setUp(self):
        self.response=SnapshotResponse(200,b'{}',"a"*64,"https://id.example/snapshot")
        self.fetch=MagicMock(return_value=self.response)
        self.kw=dict(connection=MagicMock(),fetch=self.fetch,
            url="https://id.example/snapshot",expected_host="id.example",
            tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            issuer="https://id.example",secret=b"x"*32)
    @patch("app.hitl_idp_transport.publish_signed_idp_snapshot",return_value=True)
    def test_transport_forwards_to_signature_verifier(self,publish):
        self.assertTrue(ingest_trusted_idp_snapshot(**self.kw))
        self.fetch.assert_called_once_with(url=self.kw["url"],max_bytes=4194304,
            connect_timeout=3,total_timeout=10,follow_redirects=False)
        publish.assert_called_once()
    def test_redirect_denied(self):
        self.response=SnapshotResponse(302,b'',"a"*64,self.kw["url"])
        self.fetch.return_value=self.response
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
    def test_changed_final_url_denied(self):
        self.fetch.return_value=SnapshotResponse(200,b'{}',"a"*64,
                                                  "https://evil.example/snapshot")
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
    def test_oversized_body_denied(self):
        self.kw["max_bytes"]=4
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
    def test_untrusted_host_denied_before_fetch(self):
        self.kw["url"]="https://evil.example/snapshot"
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
        self.fetch.assert_not_called()
    def test_excessive_deadline_denied(self):
        self.kw["total_timeout"]=60
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
        self.fetch.assert_not_called()
    def test_missing_fetch_denied(self):
        self.kw["fetch"]=None
        with self.assertRaises(SnapshotRejected):
            ingest_trusted_idp_snapshot(**self.kw)
if __name__=="__main__":
    unittest.main()
