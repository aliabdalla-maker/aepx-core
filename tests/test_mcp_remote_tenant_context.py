"""Offline fail-closed tests for runtime role and tenant binding."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_remote_tenant_context import bind_verified_tenant, UnsafeTenantContext

class Cursor:
    def __init__(self, role="aepx_runtime", flags=(False, False), security="on"):
        self.role, self.flags, self.security = role, flags, security
        self.queries = []
        self.last = ""
        self.tenant = None
    def execute(self, sql, args=None):
        self.last = sql
        self.queries.append(sql)
        if "set_config" in sql:
            self.tenant = args[0]
    def fetchone(self):
        if "current_user, current_setting" in self.last:
            return self.role, self.security
        if "pg_catalog.pg_roles" in self.last:
            return self.flags
        if "set_config" in self.last:
            return (self.tenant,)
        return None

class TenantContextTests(unittest.TestCase):
    def setUp(self):
        self.tenant = str(uuid4())
    def bind(self, cursor, **kwargs):
        args=dict(verified_tenant_id=self.tenant, expected_runtime_role="aepx_runtime")
        args.update(kwargs)
        return bind_verified_tenant(cursor, **args)
    def test_allowed_role_binds_transaction_local_tenant(self):
        cur=Cursor()
        self.assertEqual(self.bind(cur), self.tenant)
        self.assertTrue(any("set_config('app.tenant_id', %s, true)" in q for q in cur.queries))
    def test_bypass_and_superuser_roles_denied(self):
        for flags in ((True,False),(False,True),(True,True),None):
            with self.subTest(flags=flags):
                cur=Cursor(flags=flags)
                with self.assertRaises(UnsafeTenantContext):
                    self.bind(cur)
                self.assertFalse(any("set_config" in q for q in cur.queries))
    def test_wrong_role_or_disabled_rls_denied(self):
        for cur in (Cursor(role="postgres"),Cursor(security="off")):
            with self.assertRaises(UnsafeTenantContext):
                self.bind(cur)
    def test_bad_tenant_denied(self):
        for tenant in ("invalid",None,1,str(uuid4()).upper()):
            with self.subTest(tenant=tenant),self.assertRaises(UnsafeTenantContext):
                self.bind(Cursor(),verified_tenant_id=tenant)

if __name__ == "__main__":
    unittest.main()
