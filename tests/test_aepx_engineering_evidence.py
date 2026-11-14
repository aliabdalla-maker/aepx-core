"""Offline evidence verification tests."""
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_engineering_evidence import digest_artifact, verify_iteration_artifacts, EvidenceDenied
from scripts.aepx_engineering_iteration_state import advance, STAGES

class EvidenceTests(unittest.TestCase):
    def test_verified_artifacts_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            state={"version":1,"iterations":[]}
            manifest={}
            for stage in STAGES:
                filename=stage+".txt"
                (root/filename).write_text("evidence for "+stage)
                manifest[stage]=filename
                state=advance(state,number=1,stage=stage,
                              evidence=digest_artifact(root,filename))
            self.assertTrue(verify_iteration_artifacts(state,1,root,manifest))
            (root/"tests_recorded.txt").write_text("tampered")
            with self.assertRaises(EvidenceDenied):
                verify_iteration_artifacts(state,1,root,manifest)

    def test_symlink_and_traversal_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            (root/"valid.txt").write_text("safe")
            (root/"alias.txt").symlink_to(root/"valid.txt")
            for path in ("alias.txt","../valid.txt"):
                with self.subTest(path=path), self.assertRaises(EvidenceDenied):
                    digest_artifact(root,path)

    def test_symlinked_parent_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            (root/"real").mkdir()
            (root/"real"/"artifact.txt").write_text("artifact")
            (root/"alias").symlink_to(root/"real",target_is_directory=True)
            with self.assertRaises(EvidenceDenied):
                digest_artifact(root,"alias/artifact.txt")

    def test_fifo_is_not_read(self):
        import os
        if not hasattr(os,"mkfifo"):
            self.skipTest("POSIX FIFO unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            os.mkfifo(root/"pipe")
            with self.assertRaises(EvidenceDenied):
                digest_artifact(root,"pipe")

    def test_unverified_string_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            state={"version":1,"iterations":[]}
            for stage in STAGES:
                (root/(stage+".txt")).write_text(stage)
                state=advance(state,number=1,stage=stage,evidence="unverified")
            with self.assertRaises(EvidenceDenied):
                verify_iteration_artifacts(state,1,root,{s:s+".txt" for s in STAGES})

if __name__=="__main__":
    unittest.main()
