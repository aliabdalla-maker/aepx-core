import importlib.util
import pathlib
import unittest
from uuid import UUID
p=pathlib.Path(__file__).resolve().parents[1]/"services/governance/app/hitl_authz.py"
spec=importlib.util.spec_from_file_location("hitl_authz",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
T=UUID("11111111-1111-4111-8111-111111111111")
OTHER=UUID("22222222-2222-4222-8222-222222222222")
def principal(roles):
    return m.VerifiedPrincipal("alice",T,frozenset(roles),"trusted-issuer")
class AuthzTests(unittest.TestCase):
    def test_request_role(self):
        self.assertEqual(m.authorize_request(principal({"hitl:request"}),tenant_id=T),"alice")
    def test_cross_tenant_denied(self):
        with self.assertRaises(m.AuthorizationDenied):
            m.authorize_request(principal({"hitl:request"}),tenant_id=OTHER)
    def test_self_approval_denied(self):
        with self.assertRaises(m.AuthorizationDenied):
            m.authorize_decision(principal({"hitl:approve"}),tenant_id=T,requester_id="alice")
    def test_separate_approver_allowed(self):
        self.assertEqual(m.authorize_decision(principal({"hitl:approve"}),tenant_id=T,requester_id="bob"),"alice")
    def test_unverified_denied(self):
        with self.assertRaises(m.AuthorizationDenied):
            m.authorize_consume({"subject":"alice","roles":["hitl:execute"]},tenant_id=T)
    def test_wrong_role_denied(self):
        with self.assertRaises(m.AuthorizationDenied):
            m.authorize_consume(principal({"hitl:approve"}),tenant_id=T)
if __name__=="__main__":unittest.main()
