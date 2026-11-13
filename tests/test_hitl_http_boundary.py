"""Offline HTTP security tests. Never connects to PostgreSQL or a live IdP."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.main import app
from app.hitl_authz import VerifiedPrincipal

class HitlApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.tenant=uuid4()
        self.body={"tenant_id":str(self.tenant),"approval_id":str(uuid4()),
                   "action":{"operation":"test"},"idempotency_key":"test-unique-123"}
    def test_missing_token_denied(self):
        self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,403)
    def test_bad_token_denied(self):
        self.assertEqual(self.client.post("/hitl/consume",json=self.body,headers={"Authorization":"Bearer invalid"}).status_code,403)
    def test_other_tenant_denied(self):
        p=VerifiedPrincipal("worker",uuid4(),frozenset({"hitl:execute"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=p):
            self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,403)
    def test_missing_role_denied(self):
        p=VerifiedPrincipal("worker",self.tenant,frozenset({"hitl:approve"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=p):
            self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,403)
    def test_no_database_fails_closed(self):
        p=VerifiedPrincipal("worker",self.tenant,frozenset({"hitl:execute"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=p),patch.dict(os.environ,{"HITL_DATABASE_URL":""}):
            self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,503)
    def test_malformed_idempotency_key_rejected(self):
        self.body["idempotency_key"]="bad key with spaces"
        self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,422)
    def test_unicode_idempotency_key_rejected(self):
        self.body["idempotency_key"]="répétition-1234"
        self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,422)
    def test_approved_request_enqueues_only(self):
        from unittest.mock import MagicMock
        p=VerifiedPrincipal("worker",self.tenant,frozenset({"hitl:execute"}),"issuer")
        fake=MagicMock()
        fake.__enter__.return_value=fake
        with patch("app.hitl_api.verify_bearer",return_value=p),patch.dict(os.environ,{"HITL_DATABASE_URL":"postgresql://test"}),patch("psycopg.connect",return_value=fake),patch("app.hitl_api.consume_with_outbox",return_value="event-123") as enqueue:
            response=self.client.post("/hitl/consume",json=self.body)
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json(),{"status":"queued","event_id":"event-123"})
        self.assertEqual(enqueue.call_args.kwargs["actor_id"],"worker")
        self.assertEqual(str(enqueue.call_args.kwargs["tenant_id"]),str(self.tenant))
    def test_persistence_error_is_redacted(self):
        p=VerifiedPrincipal("worker",self.tenant,frozenset({"hitl:execute"}),"issuer")
        with patch("app.hitl_api.verify_bearer",return_value=p),patch.dict(os.environ,{"HITL_DATABASE_URL":"postgresql://test"}),patch("psycopg.connect",side_effect=RuntimeError("secret database password")):
            response=self.client.post("/hitl/consume",json=self.body)
        self.assertEqual(response.status_code,503)
        self.assertNotIn("secret",response.text)
    def test_empty_action_rejected(self):
        self.body["action"]={}
        self.assertEqual(self.client.post("/hitl/consume",json=self.body).status_code,422)
if __name__=="__main__":unittest.main()
