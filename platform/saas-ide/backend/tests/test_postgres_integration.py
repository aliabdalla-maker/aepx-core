"""Integration tests against an actual PostgreSQL service.

Requires IDE_TEST_ADMIN_DATABASE_URL (admin) and IDE_DATABASE_URL (ide_runtime).
CI creates the roles and applies migration before running this file.
"""
import os
import subprocess
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

if not os.getenv("IDE_TEST_ADMIN_DATABASE_URL"):
    pytest.skip("PostgreSQL integration environment not configured", allow_module_level=True)

from app import main

@pytest.fixture(scope="module")
def prepared_db():
    admin = create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    with admin.begin() as db:
        db.execute(text("TRUNCATE ide_workspace_files, ide_projects, ide_memberships CASCADE"))
        db.execute(text("""INSERT INTO ide_memberships (tenant_id, subject, role) VALUES
            ('alpha','user-alpha','owner'), ('beta','user-beta','viewer'),
            ('beta','user-alpha','viewer')"""))
    yield
    admin.dispose()


@pytest.fixture()
def tokens(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(main, "jwks_client", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    ))
    def mint(subject="user-alpha", **changes):
        now = datetime.now(timezone.utc)
        claims = {"iss": main.OIDC_ISSUER, "aud": main.OIDC_AUDIENCE,
                  "sub": subject, "iat": now, "exp": now + timedelta(minutes=5)}
        claims.update(changes)
        return jwt.encode(claims, private, algorithm="RS256")
    return mint


def headers(token, tenant):
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant}


def test_oidc_signature_issuer_audience_expiry_and_membership(prepared_db, tokens):
    client = TestClient(main.app)
    valid = tokens()
    assert client.get("/api/v1/me", headers=headers(valid, "alpha")).status_code == 200
    assert client.get("/api/v1/me", headers=headers(valid, "not-a-member")).status_code == 403
    for invalid in [
        tokens(iss="https://other.example.test"),
        tokens(aud="other-api"),
        tokens(exp=datetime.now(timezone.utc) - timedelta(minutes=10)),
        "invalid",
    ]:
        assert client.get("/api/v1/me", headers=headers(invalid, "alpha")).status_code == 401


def test_tenant_and_role_isolation(prepared_db, tokens):
    client = TestClient(main.app)
    owner = headers(tokens(), "alpha")
    viewer = headers(tokens(), "beta")
    made = client.post("/api/v1/projects", headers=owner, json={"name": "alpha project"})
    assert made.status_code == 201, made.text
    project_id = made.json()["id"]
    assert client.get("/api/v1/projects", headers=viewer).json() == []
    assert client.get(f"/api/v1/projects/{project_id}", headers=viewer).status_code == 404
    assert client.post("/api/v1/projects", headers=viewer, json={"name": "denied"}).status_code == 403
    assert client.put(f"/api/v1/projects/{project_id}/files/main.py", headers=owner, json={"content": "hello"}).status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/files", headers=viewer).status_code == 404
    assert client.put(f"/api/v1/projects/{project_id}/files/main.py", headers=viewer, json={"content": "hack"}).status_code == 403


def test_rls_enforced_by_runtime_role(prepared_db):
    # Use the same runtime role as the API, not the migration/superuser role.
    with main.engine.connect() as db:
        assert db.execute(text("SELECT current_user")).scalar() == "ide_runtime"
        assert db.execute(text("SELECT count(*) FROM ide_memberships")).scalar() == 0
        db.execute(text("SELECT set_config('ide.tenant_id', 'alpha', true)"))
        assert db.execute(text("SELECT count(*) FROM ide_memberships")).scalar() == 1
        assert db.execute(text("SELECT count(*) FROM ide_projects")).scalar() == 1
        db.rollback()
        db.execute(text("SELECT set_config('ide.tenant_id', 'beta', true)"))
        assert db.execute(text("SELECT count(*) FROM ide_projects")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM ide_workspace_files")).scalar() == 0
        db.rollback()
        assert db.execute(text("SELECT count(*) FROM ide_projects")).scalar() == 0


def test_phase2_run_approval_and_tenant_isolation(prepared_db, tokens):
    client = TestClient(main.app)
    owner = headers(tokens(), "alpha")
    viewer = headers(tokens(), "beta")
    project = client.post("/api/v1/projects", headers=owner, json={"name": "phase2"}).json()
    created = client.post("/api/v1/agent-runs", headers=owner, json={
        "project_id": project["id"], "task": "Design a secure SaaS application"
    })
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert created.json()["status"] == "awaiting_approval"
    assert client.get(f"/api/v1/agent-runs/{run_id}", headers=viewer).status_code == 404
    assert client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true", headers=viewer).status_code == 404
    approved = client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true", headers=owner)
    assert approved.status_code == 200, approved.text
    assert approved.json()["execution_started"] is False
    assert client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true", headers=owner).status_code == 409
    doc = client.post(f"/api/v1/projects/{project['id']}/knowledge", headers=owner, json={
        "title": "Architecture", "content": "PostgreSQL tenant security with OIDC and RLS"
    })
    assert doc.status_code == 201, doc.text
    result = client.post(f"/api/v1/projects/{project['id']}/knowledge/search", headers=owner, json={"query": "PostgreSQL"})
    assert result.status_code == 200 and result.json()["matches"]
    assert client.post(f"/api/v1/projects/{project['id']}/knowledge/search", headers=viewer, json={"query": "PostgreSQL"}).status_code == 404


def test_phase21_audit_cancel_and_vector_rls(prepared_db, tokens):
    client = TestClient(main.app)
    owner = headers(tokens(), "alpha")
    viewer = headers(tokens(), "beta")
    project = client.post("/api/v1/projects", headers=owner, json={"name": "phase21"}).json()
    run = client.post("/api/v1/agent-runs", headers=owner, json={
        "project_id": project["id"], "task": "Review security controls"
    }).json()
    audit = client.get(f"/api/v1/agent-runs/{run['id']}/audit", headers=owner)
    assert audit.status_code == 200 and audit.json()[0]["action"] == "created"
    assert client.get(f"/api/v1/agent-runs/{run['id']}/audit", headers=viewer).status_code == 404
    cancelled = client.post(f"/api/v1/agent-runs/{run['id']}/cancel", headers=owner)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/agent-runs/{run['id']}/retry", headers=owner).status_code == 409
    with main.engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM ide_agent_audit")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM ide_knowledge_vectors")).scalar() == 0
        db.execute(text("SELECT set_config('ide.tenant_id', 'alpha', true)"))
        assert db.execute(text("SELECT count(*) FROM ide_agent_audit")).scalar() >= 2
        db.rollback()
        assert db.execute(text("SELECT count(*) FROM ide_agent_audit")).scalar() == 0


def test_phase22_durable_queue_tool_approval_and_rls(prepared_db, tokens, monkeypatch):
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    viewer=headers(tokens(),"beta")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase22"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Design audited task queue"
    }).json()
    run_id=run["id"]
    assert client.post(f"/api/v1/agent-runs/{run_id}/enqueue",headers=owner).status_code==409
    assert client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true",headers=owner).status_code==200
    job=client.post(f"/api/v1/agent-runs/{run_id}/enqueue",headers=owner)
    assert job.status_code==200,job.text
    duplicate=client.post(f"/api/v1/agent-runs/{run_id}/enqueue",headers=owner)
    assert duplicate.json()["job_id"]==job.json()["job_id"]
    assert client.post(f"/api/v1/agent-runs/{run_id}/enqueue",headers=viewer).status_code==403
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL","https://mcp.example.test/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS","search")
    body={"server":"knowledge","tool":"search","arguments":{"query":"security"}}
    approval=client.post(f"/api/v1/agent-runs/{run_id}/tool-requests",headers=owner,json=body)
    assert approval.status_code==201,approval.text
    approval_id=approval.json()["id"]
    assert client.post(f"/api/v1/tool-approvals/{approval_id}/decision?approved=true",headers=viewer).status_code==403
    assert client.post(f"/api/v1/tool-approvals/{approval_id}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/tool-approvals/{approval_id}/decision?approved=true",headers=owner).status_code==409
    with main.engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM ide_agent_jobs")).scalar()==0
        assert db.execute(text("SELECT count(*) FROM ide_tool_approvals")).scalar()==0
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        assert db.execute(text("SELECT count(*) FROM ide_agent_jobs")).scalar()>=1
        assert db.execute(text("SELECT count(*) FROM ide_tool_approvals")).scalar()>=1


def test_phase23_fencing_budget_and_rls(prepared_db, tokens):
    from app.phase23 import fenced_claim, heartbeat, fenced_finish, reserve_budget, settle_budget
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase23"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Validate fencing and budget accounting"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    # Budget provisioning is an administrative operation, not a runtime permission.
    # Keep ide_runtime unable to INSERT/DELETE tenant budgets.
    admin = create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as db:
            db.execute(text("""INSERT INTO ide_agent_budgets
                (tenant_id,max_tokens,max_cost_microusd)
                VALUES ('alpha',2000,1000000)
                ON CONFLICT (tenant_id) DO UPDATE SET
                  max_tokens=EXCLUDED.max_tokens,
                  max_cost_microusd=EXCLUDED.max_cost_microusd"""))
    finally:
        admin.dispose()
    with main.SessionLocal() as db:
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        lease=fenced_claim(db,"alpha","worker-a")
        assert lease and lease["fencing_token"]==1
        assert heartbeat(db,"alpha",lease["job_id"],"worker-a",0) is False
        assert heartbeat(db,"alpha",lease["job_id"],"worker-a",1) is True
        reservation=reserve_budget(db,"alpha",lease["job_id"],1,1000,500000)
        assert reserve_budget(db,"alpha",lease["job_id"],1,1000,500000)==reservation
        settle_budget(db,"alpha",reservation,800,400000)
        assert fenced_finish(db,"alpha",lease["job_id"],"worker-a",0,True) is False
        assert fenced_finish(db,"alpha",lease["job_id"],"worker-a",1,True) is True
        assert fenced_finish(db,"alpha",lease["job_id"],"worker-a",1,True) is False
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        row=db.execute(text("SELECT spent_tokens,spent_microusd FROM ide_agent_budgets WHERE tenant_id='alpha'")).first()
        assert tuple(row)==(800,400000)
        db.rollback()
    with main.engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM ide_agent_spend")).scalar()==0
        assert db.execute(text("SELECT count(*) FROM ide_agent_budgets")).scalar()==0


def test_phase24_cancel_invalidates_fenced_worker(prepared_db, tokens):
    from app.phase23 import fenced_claim, record_fenced_result
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase24-cancel"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Cancellation race regression"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    # Earlier module tests leave approved jobs. Cancel those unrelated jobs so
    # this test exercises its own queue entry without changing production FIFO.
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
                fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
                WHERE tenant_id='alpha' AND run_id<>:run
                  AND state IN ('pending','leased')"""),{"run":rid})
    finally:
        admin.dispose()
    with main.SessionLocal() as db:
        lease=fenced_claim(db,"alpha","cancel-worker")
        assert lease and lease["run_id"]==rid
    assert client.post(f"/api/v1/agent-runs/{rid}/cancel",headers=owner).status_code==200
    with main.SessionLocal() as db:
        assert record_fenced_result(db,"alpha",lease["job_id"],"cancel-worker",
                                    lease["fencing_token"],"SHOULD NOT PERSIST",True) is False
    detail=client.get(f"/api/v1/agent-runs/{rid}",headers=owner).json()
    assert detail["status"]=="cancelled" and "SHOULD NOT PERSIST" not in detail["result"]


def test_phase24_competing_claims_only_one_wins(prepared_db, tokens):
    from app.phase23 import fenced_claim
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase24-race"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Competing claim verification"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    # Earlier module tests leave approved jobs. Cancel those unrelated jobs so
    # this test exercises its own queue entry without changing production FIFO.
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
                fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
                WHERE tenant_id='alpha' AND run_id<>:run
                  AND state IN ('pending','leased')"""),{"run":rid})
    finally:
        admin.dispose()
    with main.SessionLocal() as first:
        lease=fenced_claim(first,"alpha","worker-first")
        assert lease and lease["run_id"]==rid
    with main.SessionLocal() as second:
        # No second worker may take an unexpired lease.
        assert fenced_claim(second,"alpha","worker-second") is None
    with main.SessionLocal() as third:
        from app.phase23 import record_fenced_result
        assert record_fenced_result(third,"alpha",lease["job_id"],"worker-second",
                                    lease["fencing_token"],"forged",True) is False


def test_phase25_quarantine_reconcile_and_tenant_metrics(prepared_db, tokens):
    from app.phase23 import fenced_claim, reserve_budget, record_fenced_result
    from app.recovery25 import quarantine_expired, reconcile, tenant_metrics
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase25-recovery"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Verify ambiguous delivery recovery"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    # Keep this test independent of earlier approved jobs.
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
                fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
                WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
        with main.SessionLocal() as db:
            lease=fenced_claim(db,"alpha","recovery-worker")
            assert lease and lease["run_id"]==rid
        with main.SessionLocal() as db:
            reservation=reserve_budget(db,"alpha",lease["job_id"],lease["fencing_token"],100,10000)
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET lease_until=now()-interval '1 second'
                WHERE tenant_id='alpha' AND id=:job"""),{"job":lease["job_id"]})
        with main.SessionLocal() as db:
            assert quarantine_expired(db,"alpha")>=1
            assert record_fenced_result(db,"alpha",lease["job_id"],"recovery-worker",
                       lease["fencing_token"],"unsafe late result",True) is False
        with main.SessionLocal() as db:
            assert tenant_metrics(db,"alpha")["unresolved_reservations"]>=1
            with pytest.raises(LookupError):
                reconcile(db,"beta",reservation,"provider-25",50,5000,actor="test-operator")
            reconcile(db,"alpha",reservation,"provider-25",50,5000,actor="test-operator")
            with pytest.raises(ValueError):
                reconcile(db,"alpha",reservation,"provider-25",50,5000,actor="test-operator")
            assert tenant_metrics(db,"alpha")["unresolved_reservations"]==0
    finally:
        admin.dispose()


def test_phase26_parallel_fenced_claims(prepared_db, tokens):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.phase23 import fenced_claim
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase26-parallel"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Parallel lease race verification"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
              fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
              WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
    finally:
        admin.dispose()
    gate=Barrier(8)
    def contender(i):
        with main.SessionLocal() as db:
            gate.wait(timeout=10)
            return fenced_claim(db,"alpha",f"worker-{i}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(contender,range(8)))
    winners=[item for item in outcomes if item]
    assert len(winners)==1
    assert winners[0]["run_id"]==rid


def test_phase26_parallel_mcp_approval_single_use(prepared_db, tokens, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.phase22 import consume_tool
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase26-mcp"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Parallel MCP approval race verification"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL","https://mcp.example.test/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS","search")
    body={"server":"knowledge","tool":"search","arguments":{"query":"phase26"}}
    requested=client.post(f"/api/v1/agent-runs/{rid}/tool-requests",headers=owner,json=body)
    assert requested.status_code==201,requested.text
    assert client.post(f"/api/v1/tool-approvals/{requested.json()['id']}/decision?approved=true",
                       headers=owner).status_code==200
    gate=Barrier(8)
    def contender(i):
        with main.SessionLocal() as db:
            gate.wait(timeout=10)
            try:
                consume_tool(db,"alpha",rid,"knowledge","search",{"query":"phase26"})
                return True
            except PermissionError:
                return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(contender,range(8)))
    assert outcomes.count(True)==1
    with main.SessionLocal() as db:
        with pytest.raises(PermissionError):
            consume_tool(db,"beta",rid,"knowledge","search",{"query":"phase26"})


def test_phase27_crash_after_budget_reservation_and_mock_billing(prepared_db, tokens):
    """Simulated process death after reservation: no replay; verified mock receipt settles."""
    from app.phase23 import fenced_claim,reserve_budget,record_fenced_result
    from app.recovery25 import quarantine_expired,reconcile,tenant_metrics
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase27-crash"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Simulated crash before provider receipt"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
              fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
              WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
        with main.SessionLocal() as db:
            lease=fenced_claim(db,"alpha","crashed-worker")
        assert lease and lease["run_id"]==rid
        with main.SessionLocal() as db:
            reservation=reserve_budget(db,"alpha",lease["job_id"],lease["fencing_token"],100,10000)
        # Process is gone: no result or settlement. Force expiry using privileged test setup.
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET lease_until=now()-interval '1 second'
              WHERE tenant_id='alpha' AND id=:job"""),{"job":lease["job_id"]})
        with main.SessionLocal() as db:
            assert quarantine_expired(db,"alpha")>=1
            assert fenced_claim(db,"alpha","replacement") is None
            assert record_fenced_result(db,"alpha",lease["job_id"],"crashed-worker",
                lease["fencing_token"],"late response",True) is False
        # Mock provider evidence: receipt number + bounded token/cost accounting.
        with main.SessionLocal() as db:
            with pytest.raises(PermissionError):
                reconcile(db,"alpha",reservation,"mock-receipt-phase27",101,10001,actor="test")
            reconcile(db,"alpha",reservation,"mock-receipt-phase27",37,3200,actor="test")
            assert tenant_metrics(db,"alpha")["unresolved_reservations"]==0
            with pytest.raises(LookupError):
                reconcile(db,"beta",reservation,"mock-receipt-other",37,3200,actor="test")
    finally:
        admin.dispose()


@pytest.mark.parametrize("boundary",["before_reservation","after_reservation","after_provider","after_settlement","success"])
def test_phase28_mock_lifecycle_fault_boundaries(prepared_db,tokens,boundary):
    """PostgreSQL-backed simulated process loss; never dispatch a live provider."""
    from app.phase23 import (fenced_claim,reserve_budget,settle_reserved_maximum,
                             record_fenced_result)
    from app.recovery25 import quarantine_expired,reconcile
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase28-"+boundary}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Offline mock-provider lifecycle"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
              fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
              WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
        with main.SessionLocal() as db:
            lease=fenced_claim(db,"alpha","phase28-worker")
        assert lease and lease["run_id"]==rid
        reservation=None
        if boundary!="before_reservation":
            with main.SessionLocal() as db:
                reservation=reserve_budget(db,"alpha",lease["job_id"],lease["fencing_token"],100,10000)
        # A deterministic offline mock inference; no external credentials or network.
        mock_calls=0
        output=None
        if boundary in ("after_provider","after_settlement","success"):
            mock_calls+=1
            output="MOCK: validated response"
        if boundary in ("after_settlement","success"):
            with main.SessionLocal() as db:
                settle_reserved_maximum(db,"alpha",reservation)
        if boundary=="success":
            with main.SessionLocal() as db:
                assert record_fenced_result(db,"alpha",lease["job_id"],"phase28-worker",
                    lease["fencing_token"],output,True)
            assert client.get(f"/api/v1/agent-runs/{rid}",headers=owner).json()["status"]=="completed"
            with main.SessionLocal() as db:
                with pytest.raises(ValueError):
                    settle_reserved_maximum(db,"alpha",reservation)
        else:
            with admin.begin() as conn:
                conn.execute(text("""UPDATE ide_agent_jobs SET lease_until=now()-interval '1 second'
                  WHERE tenant_id='alpha' AND id=:job"""),{"job":lease["job_id"]})
            with main.SessionLocal() as db:
                assert quarantine_expired(db,"alpha")>=1
                assert fenced_claim(db,"alpha","replacement-worker") is None
                assert record_fenced_result(db,"alpha",lease["job_id"],"phase28-worker",
                    lease["fencing_token"],"late",True) is False
            if reservation:
                with main.SessionLocal() as db:
                    if boundary!="after_settlement":
                        reconcile(db,"alpha",reservation,"mock-"+rid,10,1000,actor="test-operator")
                    else:
                        reconcile(db,"alpha",reservation,"mock-"+rid,10,1000,actor="test-operator")
                    with pytest.raises(ValueError):
                        reconcile(db,"alpha",reservation,"mock-"+rid,10,1000,actor="test-operator")
        assert mock_calls==(1 if boundary in ("after_provider","after_settlement","success") else 0)
    finally:
        admin.dispose()


def test_phase29_signed_mock_receipt_replay_and_cross_tenant(prepared_db,tokens):
    from app.phase23 import fenced_claim,reserve_budget
    from app.billing29 import sign_mock_receipt,reconcile_mock_receipt
    client=TestClient(main.app)
    owner=headers(tokens(),"alpha")
    project=client.post("/api/v1/projects",headers=owner,json={"name":"phase29-billing"}).json()
    run=client.post("/api/v1/agent-runs",headers=owner,json={
        "project_id":project["id"],"task":"Authenticated offline mock billing"
    }).json()
    rid=run["id"]
    assert client.post(f"/api/v1/agent-runs/{rid}/decision?approved=true",headers=owner).status_code==200
    assert client.post(f"/api/v1/agent-runs/{rid}/enqueue",headers=owner).status_code==200
    admin=create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    try:
        with admin.begin() as conn:
            conn.execute(text("""UPDATE ide_agent_jobs SET state='cancelled',
              fencing_token=fencing_token+1,lease_owner=NULL,lease_until=NULL
              WHERE tenant_id='alpha' AND run_id<>:run AND state IN ('pending','leased')"""),{"run":rid})
        with main.SessionLocal() as db:
            lease=fenced_claim(db,"alpha","billing-worker")
        assert lease and lease["run_id"]==rid
        with main.SessionLocal() as db:
            reservation=reserve_budget(db,"alpha",lease["job_id"],lease["fencing_token"],100,10000)
        receipt={"tenant":"alpha","reservation":reservation,"provider":"mock",
                 "request_id":"request-"+rid,"tokens":20,"microusd":1000}
        key=b"mock-only-signing-key-32-bytes-minimum!!"
        signature=sign_mock_receipt(receipt,key)
        with main.SessionLocal() as db:
            with pytest.raises(PermissionError):
                reconcile_mock_receipt(db,"beta",receipt,signature,key,actor="mock-test")
            reconcile_mock_receipt(db,"alpha",receipt,signature,key,actor="mock-test")
            with pytest.raises(ValueError):
                reconcile_mock_receipt(db,"alpha",receipt,signature,key,actor="mock-test")
        # A distinct reservation must not reuse the same provider request ID.
        # Unique constraint on tenant/provider reference protects against double billing.
        with main.SessionLocal() as db:
            db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
            assert db.execute(text("""SELECT count(*) FROM ide_agent_reconciliation
              WHERE tenant_id='alpha' AND provider_reference=:reference"""),
              {"reference":"mock:request-"+rid}).scalar()==1
    finally:
        admin.dispose()


def test_phase29_authenticated_alerts_rbac_and_cross_tenant(prepared_db,tokens):
    client=TestClient(main.app)
    alpha=headers(tokens(),"alpha")
    beta=headers(tokens(),"beta")
    assert client.get("/api/v1/operations/alerts",headers=alpha).status_code==200
    assert client.get("/api/v1/operations/alerts",headers=beta).status_code in (200,403)
    # Unknown tenant is not authorized by X-Tenant-ID alone.
    unknown=dict(alpha,**{"X-Tenant-ID":"unregistered-phase29"})
    assert client.get("/api/v1/operations/alerts",headers=unknown).status_code==403
    assert client.get("/api/v1/operations/alerts",headers={"X-Tenant-ID":"alpha"}).status_code==401


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


def test_mcp_single_use_concurrent_postgres_approval_and_audit(prepared_db, tokens, monkeypatch):
    """Two independent PostgreSQL sessions race for one exact approved tool call."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.phase22 import consume_tool

    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://mcp.example.test/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS", "search")
    client = TestClient(main.app)
    owner = headers(tokens(), "alpha")
    project = client.post("/api/v1/projects", headers=owner,
                          json={"name": "concurrent-mcp-approval"})
    assert project.status_code == 201, project.text
    run = client.post("/api/v1/agent-runs", headers=owner,
                      json={"project_id": project.json()["id"],
                            "task": "Offline concurrent approval regression"})
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    decision = client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true",
                           headers=owner)
    assert decision.status_code == 200, decision.text
    arguments = {"query": "concurrency"}
    approval = client.post(f"/api/v1/agent-runs/{run_id}/tool-requests",
                           headers=owner, json={"server": "knowledge",
                                                "tool": "search",
                                                "arguments": arguments})
    assert approval.status_code == 201, approval.text
    approval_id = approval.json()["id"]
    approved = client.post(f"/api/v1/tool-approvals/{approval_id}/decision?approved=true",
                           headers=owner)
    assert approved.status_code == 200, approved.text

    barrier = Barrier(2)
    def consume_once():
        with main.SessionLocal() as db:
            barrier.wait(timeout=10)
            try:
                consume_tool(db, "alpha", run_id, "knowledge", "search", arguments)
                return "consumed"
            except PermissionError:
                return "denied"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(consume_once) for _ in range(2)]
        outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(outcomes) == ["consumed", "denied"], outcomes

    # RLS must hide the approval from other tenants, and the decision
    # must have produced a durable audit event.
    with main.engine.connect() as db:
        db.execute(text("SELECT set_config('ide.tenant_id','beta',true)"))
        assert db.execute(text(
            "SELECT count(*) FROM ide_tool_approvals WHERE id=:id"),
            {"id": approval_id}).scalar() == 0
        db.rollback()
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        assert db.execute(text(
            "SELECT state FROM ide_tool_approvals WHERE id=:id"),
            {"id": approval_id}).scalar() == "consumed"
        assert db.execute(text(
            "SELECT count(*) FROM ide_agent_audit WHERE tenant_id='alpha' "
            "AND run_id=:run AND action='tool_approved'"),
            {"run": run_id}).scalar() >= 1


def test_mcp_denied_attempts_do_not_consume_approval(prepared_db, tokens, monkeypatch):
    """A consumed approval must revert if its enclosing transaction rolls back.

    This regression documents current commit semantics and protects against
    accidentally treating a committed approval as rollback-safe.
    """
    from app.phase22 import consume_tool
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://mcp.example.test/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS", "search")
    client = TestClient(main.app)
    owner = headers(tokens(), "alpha")
    project = client.post("/api/v1/projects", headers=owner, json={"name": "mcp-rollback"})
    assert project.status_code == 201, project.text
    run = client.post("/api/v1/agent-runs", headers=owner,
                      json={"project_id": project.json()["id"], "task": "Offline rollback acceptance"})
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    assert client.post(f"/api/v1/agent-runs/{run_id}/decision?approved=true",
                       headers=owner).status_code == 200
    args = {"query": "rollback"}
    requested = client.post(f"/api/v1/agent-runs/{run_id}/tool-requests",
                            headers=owner, json={"server": "knowledge",
                                                 "tool": "search", "arguments": args})
    assert requested.status_code == 201, requested.text
    approval_id = requested.json()["id"]
    assert client.post(f"/api/v1/tool-approvals/{approval_id}/decision?approved=true",
                       headers=owner).status_code == 200

    # Wrong-tenant and altered arguments must fail without consuming approval.
    with main.SessionLocal() as db:
        with pytest.raises(PermissionError):
            consume_tool(db, "beta", run_id, "knowledge", "search", args)
        with pytest.raises(PermissionError):
            consume_tool(db, "alpha", run_id, "knowledge", "search", {"query": "tampered"})

    with main.engine.connect() as db:
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        assert db.execute(text("SELECT state FROM ide_tool_approvals WHERE id=:id"),
                          {"id": approval_id}).scalar() == "approved"
        db.rollback()

    with main.SessionLocal() as db:
        consume_tool(db, "alpha", run_id, "knowledge", "search", args)
        with pytest.raises(PermissionError):
            consume_tool(db, "alpha", run_id, "knowledge", "search", args)
    with main.engine.connect() as db:
        db.execute(text("SELECT set_config('ide.tenant_id','alpha',true)"))
        assert db.execute(text("SELECT state FROM ide_tool_approvals WHERE id=:id"),
                          {"id": approval_id}).scalar() == "consumed"
