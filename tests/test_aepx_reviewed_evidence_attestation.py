"""Offline signed reviewed evidence attestation regression."""
import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_reviewed_evidence_attestation import (
 AttestationDenied,canonical_attestation,verify_reviewed_attestation,
 verify_reviewed_evidence_attestation
)

TENANT="11111111-1111-4111-8111-111111111111"
KEY=b"trusted-test-key-32-bytes-long-only!!!"
STAGES=("requirements","design","patch_proposed","tests_recorded","reviewed")

class ReviewedAttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.manifest={}
        self.digests={}
        for stage in STAGES:
            data=("stage:"+stage).encode()
            filename=stage+".txt"
            (self.root/filename).write_bytes(data)
            self.manifest[stage]=filename
            self.digests[stage]="sha256:"+hashlib.sha256(data).hexdigest()
        self.state={"version":1,"iterations":[{"number":1,"stage":"reviewed","evidence":self.digests.copy()}]}
        self.env={"tenant_id":TENANT,"iteration_number":1,"lease_fence":7,
                  "worker_id":"worker-one","reviewer_id":"reviewer-one",
                  "expires_at":2000000000,"stage_digests":self.digests.copy()}
        self.sig=self.sign()
    def sign(self):
        return hmac.new(KEY,canonical_attestation(self.env),hashlib.sha256).hexdigest()
    def verify(self,**overrides):
        params={"tenant_id":TENANT,"lease_fence":7,"worker_id":"worker-one","now":1900000000}
        params.update(overrides)
        return verify_reviewed_evidence_attestation(
            self.state,1,self.root,self.manifest,self.env,self.sig,KEY,**params)
    def test_valid_scoped_attestation_and_bytes(self):
        self.assertTrue(self.verify())
    def test_wrong_tenant_worker_fence_denied(self):
        for kwargs in ({"tenant_id":"22222222-2222-4222-8222-222222222222"},
                       {"worker_id":"worker-two"},{"lease_fence":8}):
            with self.subTest(kwargs=kwargs),self.assertRaises(AttestationDenied):
                self.verify(**kwargs)
    def test_expired_denied(self):
        with self.assertRaises(AttestationDenied): self.verify(now=2000000000)
    def test_modified_artifact_denied(self):
        (self.root/"reviewed.txt").write_text("tampered")
        with self.assertRaises(AttestationDenied): self.verify()
    def test_modified_signed_digest_denied(self):
        self.env["stage_digests"]["design"]="sha256:"+("f"*64)
        with self.assertRaises(AttestationDenied): self.verify()
    def test_signature_tamper_denied(self):
        self.sig="0"*64
        with self.assertRaises(AttestationDenied): self.verify()
    def test_weak_key_denied(self):
        with self.assertRaises(AttestationDenied):
            verify_reviewed_attestation(self.env,self.sig,b"weak",
                tenant_id=TENANT,iteration_number=1,lease_fence=7,
                worker_id="worker-one",stage_digests=self.digests,now=1900000000)
    def test_bool_fence_denied(self):
        with self.assertRaises(AttestationDenied): self.verify(lease_fence=True)

if __name__=="__main__": unittest.main()
