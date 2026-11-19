"""Offline SQL interaction tests for MCP atomic claim; real PostgreSQL tests remain required."""
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_atomic_claim import claim_approved_mcp_call
from app.mcp_contract_gate import MCPContractDenied

class Result:
    def __init__(self,row): self.row=row
    def mappings(self): return self
    def first(self): return self.row

class FakeDB:
    def __init__(self,approval=None,run=True,claimed=True):
        self.approval=approval;self.run=run;self.claimed=claimed
        self.committed=False;self.rolled_back=False;self.statements=[]
    def execute(self,statement,params):
        sql=str(statement);self.statements.append(sql)
        if "set_config" in sql: return Result(None)
        if "SELECT id FROM ide_agent_runs" in sql: return Result(("run-a",) if self.run else None)
        if "SELECT a.server_name" in sql: return Result(self.approval)
        if "UPDATE ide_mcp_executions" in sql:
            return Result((self.approval["idempotency_key"],) if self.claimed else None)
        raise AssertionError(sql)
    def commit(self): self.committed=True
    def rollback(self): self.rolled_back=True

class TestAtomicClaim(unittest.TestCase):
    def fixture(self):
        row={"server_name":"crm-prod","tool_name":"crm.update",
             "args_sha256":hashlib.sha256(b'{"x":1}').hexdigest(),
             "idempotency_key":"stable-1"}
        args=dict(tenant_id="tenant-a",run_id="run-a",approval_id="approval-a",
                  server_id="crm-prod",tool_name="crm.update",arguments={"x":1},
                  allowed_tools={"crm.update"})
        return row,args
    def test_success_claims_only_after_contract_check(self):
        row,args=self.fixture();db=FakeDB(row)
        result=claim_approved_mcp_call(db,**args)
        self.assertEqual(result["idempotency_key"],"stable-1")
        self.assertTrue(db.committed)
        self.assertFalse(db.rolled_back)
        self.assertTrue(any("FOR UPDATE OF a,e" in sql for sql in db.statements))
    def test_rejects_before_claim_or_rolls_back(self):
        row,args=self.fixture()
        cases=[(None,args,True,True),
               (row,{**args,"arguments":{"x":2}},True,True),
               (row,{**args,"server_id":"rogue"},True,True),
               (row,{**args,"tool_name":"crm.delete"},True,True),
               (row,args,False,True),
               (row,args,True,False)]
        for approval,kw,run,claimed in cases:
            db=FakeDB(approval,run,claimed)
            with self.subTest(kw=kw,run=run,claimed=claimed),self.assertRaises(MCPContractDenied):
                claim_approved_mcp_call(db,**kw)
            self.assertFalse(db.committed)
            self.assertTrue(db.rolled_back)
