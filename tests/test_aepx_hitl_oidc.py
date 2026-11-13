import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock
root=pathlib.Path(__file__).resolve().parents[1]
app=types.ModuleType("app")
app.__path__=[str(root/"services/governance/app")]
sys.modules.setdefault("app",app)
path=root/"services/governance/app/hitl_oidc.py"
spec=importlib.util.spec_from_file_location("hitl_oidc",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ENV={"HITL_OIDC_ISSUER":"https://id.example.test","HITL_OIDC_AUDIENCE":"aepx-hitl",
     "HITL_OIDC_JWKS_URL":"https://id.example.test/.well-known/jwks.json"}
CLAIMS={"sub":"alice","tenant_id":"11111111-1111-4111-8111-111111111111",
        "roles":["hitl:approve"]}
class VerifierTests(unittest.TestCase):
    def test_valid_verified_claims(self):
        jwt=MagicMock()
        jwt.decode.return_value=CLAIMS
        key=MagicMock()
        key.get_signing_key_from_jwt.return_value.key="key"
        principal=m.verify_bearer("Bearer signed.token.value",env=ENV,key_client=key,jwt_module=jwt)
        self.assertEqual(principal.subject,"alice")
        self.assertIn("hitl:approve",principal.roles)
        self.assertEqual(jwt.decode.call_args.kwargs["algorithms"],["RS256","ES256"])
    def test_missing_config_denied(self):
        with self.assertRaises(m.AuthenticationDenied):
            m.verify_bearer("Bearer token",env={})
    def test_cross_host_jwks_denied(self):
        with self.assertRaises(m.AuthenticationDenied):
            m.verify_bearer("Bearer token",env={**ENV,"HITL_OIDC_JWKS_URL":"https://evil.test/jwks"})
    def test_missing_bearer_denied(self):
        with self.assertRaises(m.AuthenticationDenied):
            m.verify_bearer("token",env=ENV)
    def test_invalid_roles_denied(self):
        jwt=MagicMock()
        jwt.decode.return_value={**CLAIMS,"roles":"hitl:approve"}
        with self.assertRaises(m.AuthenticationDenied):
            m.verify_bearer("Bearer signed.token.value",env=ENV,key_client=MagicMock(),jwt_module=jwt)
    def test_invalid_signature_denied(self):
        jwt=MagicMock()
        jwt.decode.side_effect=ValueError("signature invalid")
        with self.assertRaises(m.AuthenticationDenied):
            m.verify_bearer("Bearer signed.token.value",env=ENV,key_client=MagicMock(),jwt_module=jwt)
if __name__=="__main__":unittest.main()
