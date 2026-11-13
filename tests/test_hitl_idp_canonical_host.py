import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_idp_signed_connector import validate_pinned_snapshot_url
from app.hitl_identity_snapshot import SnapshotRejected

class CanonicalHostTests(unittest.TestCase):
    def test_valid_canonical_host(self):
        for url in ("https://id.example/snapshots","https://id.example/"):
            with self.subTest(url=url):
                self.assertEqual(validate_pinned_snapshot_url(url,expected_host="id.example"),url)
    def test_ambiguous_host_rejected(self):
        cases=[
            ("https://id.example./snapshot","id.example."),
            ("https://127.0.0.1/snapshot","127.0.0.1"),
            ("https://id_example/snapshot","id_example"),
            ("https://-id.example/snapshot","-id.example"),
            ("https://id-.example/snapshot","id-.example"),
            ("https://id.example@evil.example/snapshot","evil.example"),
            ("https://id.example\\@evil.example/snapshot","evil.example"),
            ("https://id.example:444/snapshot","id.example"),
            ("https://id.example/snapshot?token=abc","id.example"),
            ("https://id.example/snapshot#fragment","id.example"),
        ]
        for url,host in cases:
            with self.subTest(url=url),self.assertRaises(SnapshotRejected):
                validate_pinned_snapshot_url(url,expected_host=host)
    def test_unicode_and_single_label_rejected(self):
        for host in ("bücher.example","localhost","internal","ID.EXAMPLE"):
            with self.subTest(host=host),self.assertRaises(SnapshotRejected):
                validate_pinned_snapshot_url("https://"+host+"/snapshot",expected_host=host)
if __name__=="__main__":
    unittest.main()
