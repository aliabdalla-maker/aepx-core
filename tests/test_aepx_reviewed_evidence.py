"""Offline pre-completion evidence checks; no approval or dispatch."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_engineering_evidence import (
    EvidenceDenied, verify_reviewed_iteration_artifacts
)
from scripts.aepx_engineering_iteration_state import STAGES

class ReviewedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.manifest={}
        self.evidence={}
        for stage in STAGES[:-1]:
            name=stage+".txt"
            payload=("evidence:"+stage).encode()
            (self.root/name).write_bytes(payload)
            self.manifest[stage]=name
            self.evidence[stage]="sha256:"+hashlib.sha256(payload).hexdigest()
        self.state={"version":1,"iterations":[
            {"number":1,"stage":"reviewed","evidence":dict(self.evidence)}
        ]}
    def test_all_five_reviewed_artifacts_verified(self):
        self.assertTrue(verify_reviewed_iteration_artifacts(
            self.state,1,self.root,self.manifest))
    def test_modified_artifact_denied(self):
        (self.root/"design.txt").write_text("tampered")
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,1,self.root,self.manifest)
    def test_missing_artifact_denied(self):
        (self.root/"reviewed.txt").unlink()
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,1,self.root,self.manifest)
    def test_extra_or_missing_manifest_entry_denied(self):
        for bad in ({**self.manifest,"completed":"fake"}, {k:v for k,v in self.manifest.items() if k!="reviewed"}):
            with self.subTest(bad=bad),self.assertRaises(EvidenceDenied):
                verify_reviewed_iteration_artifacts(self.state,1,self.root,bad)
    def test_not_reviewed_denied(self):
        self.state["iterations"][0]["stage"]="completed"
        self.state["iterations"][0]["evidence"]["completed"]="sha256:"+("a"*64)
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,1,self.root,self.manifest)
    def test_digest_reference_not_canonical_denied(self):
        self.state["iterations"][0]["evidence"]["design"]="sha256:invalid"
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,1,self.root,self.manifest)
    def test_symlink_artifact_denied(self):
        (self.root/"design.txt").unlink()
        (self.root/"design.txt").symlink_to(self.root/"requirements.txt")
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,1,self.root,self.manifest)
    def test_boolean_iteration_number_denied(self):
        with self.assertRaises(EvidenceDenied):
            verify_reviewed_iteration_artifacts(self.state,True,self.root,self.manifest)

if __name__=="__main__": unittest.main()
