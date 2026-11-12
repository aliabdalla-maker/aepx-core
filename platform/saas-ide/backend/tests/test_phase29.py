"""Offline security tests; never enable live provider execution."""
import os
import signal
import subprocess
import sys
import time
import pytest
from app.billing29 import canonical_receipt,sign_mock_receipt,verify_mock_receipt,reconcile_mock_receipt
from app.egress27 import resolve_public

KEY=b"mock-test-only-key-32-bytes-minimum!!!!"
RECEIPT={"tenant":"alpha","reservation":"res-1","provider":"mock",
         "request_id":"req-1","tokens":37,"microusd":2000}

def test_mock_receipt_tampering_and_type_confusion():
    signature=sign_mock_receipt(RECEIPT,KEY)
    verify_mock_receipt(RECEIPT,signature,KEY)
    for field,value in (("tenant","beta"),("tokens",38),("microusd",2001),("request_id","req-2")):
        modified=dict(RECEIPT,**{field:value})
        with pytest.raises(PermissionError):
            verify_mock_receipt(modified,signature,KEY)
    with pytest.raises(ValueError):
        canonical_receipt(dict(RECEIPT,tokens=True))
    with pytest.raises(PermissionError):
        verify_mock_receipt(RECEIPT,signature,b"short")

def test_mock_receipt_tenant_denial_before_database_use():
    class NeverDB:
        def execute(self,*args,**kwargs):
            raise AssertionError("Database should not be reached")
    with pytest.raises(PermissionError):
        reconcile_mock_receipt(NeverDB(),"beta",RECEIPT,
                               sign_mock_receipt(RECEIPT,KEY),KEY,actor="test")

@pytest.mark.skipif(sys.platform=="win32",reason="SIGKILL is POSIX-specific")
def test_real_sigkill_subprocess_cannot_commit_after_termination(tmp_path):
    """Real OS SIGKILL; isolated process has no DB credentials or provider keys."""
    marker=tmp_path/"should-not-exist"
    code="import time,pathlib;time.sleep(10);pathlib.Path(%r).write_text('committed')" % str(marker)
    proc=subprocess.Popen([sys.executable,"-c",code],
                          env={"PATH":os.getenv("PATH",""),"PYTHONUNBUFFERED":"1"},
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        time.sleep(.1)
        assert proc.poll() is None
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)
        assert proc.returncode!=0
        assert not marker.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def test_dns_metadata_and_private_rebinding_denied():
    for address in ("169.254.169.254","127.0.0.1","10.0.0.3","::1"):
        with pytest.raises(PermissionError):
            resolve_public("provider.example.test",resolver=lambda *a,ip=address,**kw:
                           [(2,1,6,"",(ip,443))])


def test_alerts_endpoint_requires_verified_identity_and_admin_role():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get("/api/v1/operations/alerts",headers={"X-Tenant-ID":"alpha"}).status_code==401

def test_provider_sdk_stays_disabled_without_explicit_gate(monkeypatch):
    from app.providers import generate
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        generate("openai","Never dispatch this request")

def test_mcp_stays_disabled_without_explicit_gate(monkeypatch):
    import asyncio
    from app.agent_runtime import invoke_mcp_tool
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge","search",{"q":"x"}))


@pytest.mark.skipif(sys.platform=="win32",reason="SIGKILL requires POSIX")
def test_sigkill_after_real_postgres_lease_then_quarantine(prepared_db,tokens):
    """Kill an isolated PostgreSQL lease-holder; ensure stale fence cannot persist.

    No provider network or credentials are passed to the subprocess.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine,text
    from app import main
    from app.recovery25 import quarantine_expired
    from app.phase23 import fenced_claim,record_fenced_result
    from tests.test_postgres_integration import headers
    client=TestClient(main.app)
    h=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=h,json={"name":"sigkill-lease"}).json()
    run=client.post("/api/v1/agent-runs",headers=h,json={"project_id":project["id"],"task":"Offline kill test"}).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=h).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=h).status_code==200
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
              fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
              WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
        # Subprocess claims a genuine database lease, prints fence, then sleeps.
        script="""import os,time
from app.main import SessionLocal
from app.phase23 import fenced_claim
with SessionLocal() as db:
    claim=fenced_claim(db,'alpha','killed-worker',lease_seconds=45)
assert claim is not None
print(claim['job_id']+'|'+str(claim['fencing_token']),flush=True)
time.sleep(120)
"""
        proc=subprocess.Popen([sys.executable,"-c",script],cwd=os.getcwd(),
             env={k:v for k,v in os.environ.items() if not k.startswith("IDE_LLM_") and "TOKEN" not in k},
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            line=proc.stdout.readline().strip()
            assert "|" in line,proc.stderr.read() if proc.poll() is not None else "claim failed"
            job,fence=line.split("|")
            proc.send_signal(signal.SIGKILL)
            proc.wait(timeout=5)
            with admin.begin() as conn:
                conn.execute(text("""UPDATE ide_agent_jobs SET lease_until=now()-interval '1 second'
                  WHERE tenant_id='alpha' AND id=:job"""),{"job":job})
            with main.SessionLocal() as db:
                assert quarantine_expired(db,"alpha")>=1
                assert record_fenced_result(db,"alpha",job,"killed-worker",int(fence),"late",True) is False
                assert fenced_claim(db,"alpha","replacement") is None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    finally:
        admin.dispose()
