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
