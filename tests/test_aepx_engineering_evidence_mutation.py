"""Offline tests for descriptor hashing mutation detection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.aepx_engineering_evidence import digest_artifact, EvidenceDenied

class EvidenceMutationTests(unittest.TestCase):
    def test_unchanged_regular_file_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            (root/"evidence.txt").write_text("stable")
            self.assertTrue(digest_artifact(root,"evidence.txt").startswith("sha256:"))

    def test_metadata_change_during_read_is_denied(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            path=root/"evidence.txt"
            path.write_bytes(b"before")
            original_read=os.read
            changed=[False]
            def mutate_then_read(fd, count):
                if not changed[0]:
                    changed[0]=True
                    path.write_bytes(b"after!")
                return original_read(fd,count)
            with patch("scripts.aepx_engineering_evidence.os.read",side_effect=mutate_then_read):
                with self.assertRaisesRegex(EvidenceDenied,"artifact changed"):
                    digest_artifact(root,"evidence.txt")

if __name__=="__main__":
    unittest.main()
