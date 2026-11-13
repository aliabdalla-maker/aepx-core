"""Tenant-scoped DB preflight tests using deterministic fake database rows."""
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform/saas-ide/backend"))
from app.mcp_db_preflight import prepare_mcp_db_preflight
from app.mcp_contract_gate import MCPContractDenied

class Rows:
    def __init__(self, row): self.row = row
    def mappings(self): return self
    def first(self): return self.row

class FakeDB:
    def __init__(self, row): self.row=row; self.rolled_back=False; self.sql=[]
    def execute(self, statement, params):
        self.sql.append(str(statement))
        if "SELECT set_config" in str(statement): return Rows(None)
        return Rows(self.row)
    def rollback(self): self.rolled_back=True

class TestMCPDBPreflight(unittest.TestCase):
    def fixture(self):
        row=dict(id="approval-a",tenant_id="tenant-a",run_id="run-a",
                 server_name="crm-prod",tool_name="crm.update",
                 args_sha256=hashlib.sha256(b'{"x":1}').hexdigest(),
                 state="consumed",approval_id="approval-a",
                 execution_state="reserved",idempotency_key="stable-1")
        kw=dict(tenant_id="tenant-a",run_id="run-a",approval_id="approval-a",
                server_id="crm-prod",tool_name="crm.update",arguments={"x":1},
                discovered_tools=[{"name":"crm.update"}],
                trusted_server_allowlist={"crm-prod"},
                trusted_tool_allowlist={"crm-prod":{"crm.update"}},
                request_id=7,client_name="aepx",client_version="1.0")
        return row,kw

    def test_valid_read_and_cleanup(self):
        row,kw=self.fixture()
        db=FakeDB(row)
        result=prepare_mcp_db_preflight(db,**kw)
        self.assertEqual(result["idempotency_key"],"stable-1")
        self.assertTrue(db.rolled_back)
        self.assertTrue(any("a.tenant_id=:tenant" in s for s in db.sql))

    def test_rejects_missing_or_changed_approval(self):
        row,kw=self.fixture()
        for changed in (None,{**row,"server_name":"rogue"},
                        {**row,"state":"pending"},
                        {**row,"execution_state":"dispatching"},
                        {**row,"args_sha256":"0"*64},
                        {**row,"tenant_id":"tenant-b"}):
            db=FakeDB(changed)
            with self.subTest(row=changed), self.assertRaises(MCPContractDenied):
                prepare_mcp_db_preflight(db,**kw)
            self.assertTrue(db.rolled_back)
