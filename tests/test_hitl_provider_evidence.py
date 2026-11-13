import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_provider_evidence import provider_evidence_verifier,ProviderEvidenceDenied

class ProviderEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data=dict(tenant_id=str(uuid4()),event_id=str(uuid4()),
            provider="trusted-mcp",idempotency_key="idempotency-123",
            verified_state="confirmed",evidence_reference="receipt-12345",
            reviewer_id="reviewer-123")
        self.evidence={k:self.data[k] for k in
            ("tenant_id","event_id","provider","idempotency_key")}
        self.evidence.update(state="confirmed",evidence_reference="receipt-12345",verified=True)
    def check(self,reader=None,**overrides):
        verifier=provider_evidence_verifier(trusted_provider="trusted-mcp",
            read_provider_status=reader or (lambda **kw:self.evidence))
        return verifier(**(self.data|overrides))
    def test_matching_authoritative_evidence(self):
        self.assertTrue(self.check())
    def test_mismatched_tenant(self):
        self.assertFalse(self.check(tenant_id=str(uuid4())))
    def test_mismatched_state(self):
        self.assertFalse(self.check(verified_state="failed_safe"))
    def test_wrong_provider(self):
        self.assertFalse(self.check(provider="untrusted"))
    def test_unsigned_or_unverified_evidence(self):
        self.evidence["verified"]=1
        self.assertFalse(self.check())
    def test_reader_outage_fails_closed(self):
        def broken(**kw):raise TimeoutError()
        self.assertFalse(self.check(reader=broken))
    def test_invalid_reference(self):
        self.assertFalse(self.check(evidence_reference="https://untrusted.example/receipt"))
    def test_missing_reader_denied(self):
        with self.assertRaises(ProviderEvidenceDenied):
            provider_evidence_verifier(trusted_provider="trusted-mcp",
                read_provider_status=None)
if __name__=="__main__":
    unittest.main()
