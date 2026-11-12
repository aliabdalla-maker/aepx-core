"""Offline tenant isolation, exact-argument approval, replay and audit tests."""
import os
from types import SimpleNamespace
import pytest

os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")

from app import phase22, phase23

class FakeDB:
    def __init__(self, tenant, run, server, tool, arguments):
        self.tenant=tenant
        self.run=run
        self.server=server
        self.tool=tool
        self.digest=phase22.digest_arguments(arguments)
        self.state="approved"
        self.commits=0
        self.rollbacks=0
        self.attempts=[]
        self.audit_rows=[]
    def add(self, row):
        self.audit_rows.append(row)
    def execute(self, statement, params):
        self.attempts.append(dict(params))
        if "SELECT id FROM ide_agent_runs" in str(statement):
            return SimpleNamespace(first=lambda: ("run-a",) if params["tenant"]=="tenant-a" and params["run"]=="run-a" else None)
        allowed=(params["tenant"]==self.tenant and params["run"]==self.run
                 and params["server"]==self.server and params["tool"]==self.tool
                 and params["digest"]==self.digest and self.state=="approved")
        if allowed:
            self.state="consumed"
        return SimpleNamespace(first=lambda: ("approval-1",) if allowed else None)
    def commit(self):
        self.commits+=1
    def rollback(self):
        self.rollbacks+=1

def test_tenant_and_exact_arguments_and_replay(monkeypatch):
    monkeypatch.setattr(phase23,"_scope",lambda db,tenant: None)
    args={"query":"safe"}
    db=FakeDB("tenant-a","run-a","knowledge","read",args)
    for tenant,run,server,tool,payload in (
        ("tenant-b","run-a","knowledge","read",args),
        ("tenant-a","run-b","knowledge","read",args),
        ("tenant-a","run-a","knowledge","write",args),
        ("tenant-a","run-a","unapproved","read",args),
        ("tenant-a","run-a","knowledge","read",{"query":"changed"}),
    ):
        with pytest.raises(PermissionError,match="not approved"):
            phase22.consume_tool(db,tenant,run,server,tool,payload)
        assert db.state=="approved"
    assert db.commits==0
    assert db.rollbacks==5
    phase22.consume_tool(db,"tenant-a","run-a","knowledge","read",args)
    assert db.state=="consumed" and db.commits==1
    assert len(db.audit_rows)==1
    assert db.audit_rows[0].tenant_id=="tenant-a"
    assert db.audit_rows[0].run_id=="run-a"
    assert db.audit_rows[0].action=="tool_consumed"
    with pytest.raises(PermissionError,match="already consumed"):
        phase22.consume_tool(db,"tenant-a","run-a","knowledge","read",args)
    assert db.commits==1
    assert len(db.audit_rows)==1

def test_tool_decision_rejects_non_admin_and_records_audit(monkeypatch):
    events=[]
    monkeypatch.setattr(phase22,"audit",lambda db,p,run,event: events.append((p.tenant_id,run,event)))
    item=SimpleNamespace(id="approval-1",tenant_id="tenant-a",run_id="run-a",
                         state="pending",decided_by=None)
    class DecisionDB:
        def scalar(self,query): return item
        def commit(self): pass
    db=DecisionDB()
    editor=SimpleNamespace(role="editor",tenant_id="tenant-a",subject="editor")
    owner=SimpleNamespace(role="owner",tenant_id="tenant-a",subject="owner")
    with pytest.raises(PermissionError,match="Owner/admin"):
        phase22.decide_tool(db,editor,"approval-1",True)
    assert not events and item.state=="pending"
    phase22.decide_tool(db,owner,"approval-1",False)
    assert item.state=="rejected" and item.decided_by=="owner"
    assert events==[("tenant-a","run-a","tool_rejected")]
    with pytest.raises(ValueError,match="Already decided"):
        phase22.decide_tool(db,owner,"approval-1",True)
