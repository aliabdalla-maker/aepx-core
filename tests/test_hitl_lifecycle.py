import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import MagicMock,patch
from uuid import uuid4
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.main import app
from app.hitl_authz import VerifiedPrincipal
from app.hitl_lifecycle import create_request,decide_request,DecisionConflict

class LifecycleHTTPTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.tenant=uuid4()
        self.expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    def test_request_denies_missing_auth(self):
        response=self.client.post("/hitl/requests",json={"tenant_id":str(self.tenant),"action":{"tool":"test"},"expires_at":self.expiry})
        self.assertEqual(response.status_code,403)
    def test_decision_denies_missing_auth(self):
        response=self.client.post(f"/hitl/requests/{uuid4()}/decision",json={"tenant_id":str(self.tenant),"decision":"approved"})
        self.assertEqual(response.status_code,403)
    def test_request_denies_other_tenant(self):
        principal=VerifiedPrincipal("requester",uuid4(),frozenset({"hitl:request"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=principal):
            response=self.client.post("/hitl/requests",json={"tenant_id":str(self.tenant),"action":{"tool":"test"},"expires_at":self.expiry})
        self.assertEqual(response.status_code,403)
    def test_decision_denies_wrong_role(self):
        principal=VerifiedPrincipal("approver",self.tenant,frozenset({"hitl:request"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=principal):
            response=self.client.post(f"/hitl/requests/{uuid4()}/decision",json={"tenant_id":str(self.tenant),"decision":"approved"})
        self.assertEqual(response.status_code,403)
    def test_expired_request_rejected(self):
        principal=VerifiedPrincipal("requester",self.tenant,frozenset({"hitl:request"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=principal):
            response=self.client.post("/hitl/requests",json={"tenant_id":str(self.tenant),"action":{"tool":"test"},"expires_at":"2020-01-01T00:00:00Z"})
        self.assertEqual(response.status_code,422)
    def test_invalid_decision_rejected(self):
        principal=VerifiedPrincipal("approver",self.tenant,frozenset({"hitl:approve"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=principal):
            response=self.client.post(f"/hitl/requests/{uuid4()}/decision",json={"tenant_id":str(self.tenant),"decision":"override"})
        self.assertEqual(response.status_code,422)

class LifecycleSQLTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cur=self.db.cursor.return_value.__enter__.return_value
        self.tenant=uuid4()
    def test_request_commits(self):
        create_request(self.db,tenant_id=self.tenant,action={"tool":"test"},requester_id="requester",expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        self.db.commit.assert_called_once()
    def test_decision_rejects_missing_row(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(DecisionConflict):
            decide_request(self.db,tenant_id=self.tenant,approval_id=uuid4(),approver_id="approver",decision="approved")
        self.db.rollback.assert_called_once()
    def test_decision_query_enforces_separation(self):
        self.cur.fetchone.return_value=("found",)
        decide_request(self.db,tenant_id=self.tenant,approval_id=uuid4(),approver_id="approver",decision="approved")
        sql=self.cur.execute.call_args_list[1].args[0]
        self.assertIn("requester_id<>%s",sql)
        self.assertIn("status='pending'",sql)
        self.assertIn("expires_at>now()",sql)
if __name__=="__main__":unittest.main()
