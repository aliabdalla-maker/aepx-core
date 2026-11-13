import sys
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_operator_identity import VerifiedOperator,operator_verifier

class OperatorClaimsTests(unittest.TestCase):
    def setUp(self):
        self.tenant=str(uuid4())
        self.operator=VerifiedOperator("reviewer-123",self.tenant,"https://issuer.example",
            "aepx-governance",frozenset({"hitl.remote.reconcile"}),True,2000)
        self.kw=dict(tenant_id=self.tenant,event_id=str(uuid4()),provider="sandbox-mcp",
                     reviewer_id="reviewer-123",permission="hitl.remote.reconcile",
                     verified_state="confirmed")
    def check(self,operator=None,**kw):
        return operator_verifier(operator or self.operator,trusted_issuer="https://issuer.example",
                                 trusted_audience="aepx-governance",now_epoch=1000)(**(self.kw|kw))
    def test_authorized(self):
        self.assertTrue(self.check())
    def test_wrong_tenant(self):
        self.assertFalse(self.check(tenant_id=str(uuid4())))
    def test_wrong_reviewer(self):
        self.assertFalse(self.check(reviewer_id="other-reviewer"))
    def test_wrong_permission(self):
        self.assertFalse(self.check(permission="hitl.remote.delete"))
    def test_missing_permission(self):
        self.assertFalse(self.check(replace(self.operator,permissions=frozenset())))
    def test_expired(self):
        self.assertFalse(self.check(replace(self.operator,expires_at=999)))
    def test_unverified(self):
        self.assertFalse(self.check(replace(self.operator,authenticated=False)))
    def test_wrong_issuer(self):
        self.assertFalse(self.check(replace(self.operator,issuer="https://evil.example")))
    def test_wrong_audience(self):
        self.assertFalse(self.check(replace(self.operator,audience="other-service")))
    def test_wrong_state(self):
        self.assertFalse(self.check(verified_state="uncertain"))
if __name__=="__main__":
    unittest.main()
