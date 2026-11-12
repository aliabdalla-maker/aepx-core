"""Integration tests against an actual PostgreSQL service.

Requires IDE_TEST_ADMIN_DATABASE_URL (admin) and IDE_DATABASE_URL (ide_runtime).
CI creates the roles and applies migration before running this file.
"""
import os
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
