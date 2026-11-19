import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_idp_transport import ingest_trusted_idp_snapshot
from app.hitl_idp_signed_connector import validate_pinned_snapshot_url
from app.hitl_identity_snapshot import SnapshotRejected

class TransportHardeningTests(unittest.TestCase):
    def test_nonfinite_deadlines_fail_before_fetch(self):
        for key,value in (("connect_timeout",math.nan),("total_timeout",math.nan),
                          ("connect_timeout",math.inf),("total_timeout",-math.inf)):
            with self.subTest(key=key,value=value):
                fetch=MagicMock()
                with self.assertRaises(SnapshotRejected):
                    ingest_trusted_idp_snapshot(MagicMock(),fetch=fetch,
                        url="https://id.example/snapshot",expected_host="id.example",
                        tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        issuer="https://id.example",secret=b"x"*32,**{key:value})
                fetch.assert_not_called()
    def test_local_and_query_origins_denied(self):
        for url,host in (("https://127.0.0.1/s","127.0.0.1"),
                         ("https://10.0.0.1/s","10.0.0.1"),
                         ("https://169.254.169.254/s","169.254.169.254"),
                         ("https://localhost/s","localhost"),
                         ("https://id.example/s?token=x","id.example")):
            with self.subTest(url=url),self.assertRaises(SnapshotRejected):
                validate_pinned_snapshot_url(url,expected_host=host)
    def test_public_pinned_host_allowed(self):
        self.assertEqual(validate_pinned_snapshot_url("https://id.example/s",
            expected_host="id.example"),"https://id.example/s")
if __name__=="__main__":
    unittest.main()
