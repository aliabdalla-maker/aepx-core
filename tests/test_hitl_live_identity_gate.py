import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_api import _authoritative_identity
from app.hitl_identity_policy import IdentityPolicyDenied

class LiveIdentityGateTests(unittest.TestCase):
    def test_missing_identity_dsn_fails_closed(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(HTTPException) as caught:
                _authoritative_identity("Bearer token",uuid4())
            self.assertEqual(caught.exception.status_code,503)
    @patch("app.hitl_api.verify_bearer_identity",side_effect=IdentityPolicyDenied("revoked"))
    def test_revoked_token_denied(self,verify):
        with patch.dict("os.environ",{"HITL_IDENTITY_READ_DATABASE_URL":"postgresql://localhost/identity_test"}):
            with self.assertRaises(HTTPException) as caught:
                _authoritative_identity("Bearer token",uuid4())
            self.assertEqual(caught.exception.status_code,403)
    @patch("app.hitl_api.verify_bearer_identity",side_effect=RuntimeError("database offline"))
    def test_database_outage_unavailable(self,verify):
        with patch.dict("os.environ",{"HITL_IDENTITY_READ_DATABASE_URL":"postgresql://localhost/identity_test"}):
            with self.assertRaises(HTTPException) as caught:
                _authoritative_identity("Bearer token",uuid4())
            self.assertEqual(caught.exception.status_code,503)
if __name__=="__main__":
    unittest.main()
