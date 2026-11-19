"""Integration test harness: a disposable PostgreSQL database (RLS enforced through the
non-superuser aav_app role), the real AEP-X governance service from services/governance
started as a subprocess, and an in-memory Ed25519 signing key.

Env: AAV_TEST_PG_ADMIN_DSN  superuser DSN of a scratch server (default local socket /tmp/pg:55432)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import psycopg
import pytest

HERE = Path(__file__).resolve()
CP = HERE.parents[1]
PRODUCT = HERE.parents[2]
REPO = HERE.parents[4]
ADMIN_DSN = os.getenv("AAV_TEST_PG_ADMIN_DSN", "postgresql://postgres@/postgres?host=/tmp/pg&port=55432")
DB_NAME = f"aav_t_{uuid.uuid4().hex[:8]}"
APP_PASSWORD = uuid.uuid4().hex  # servers that require passwords (CI) need one for the aav_app role


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


GOV_PORT = _free_port()
os.environ["AAV_GOVERNANCE_URL"] = f"http://127.0.0.1:{GOV_PORT}"
os.environ["AAV_FILE_STORE_DIR"] = tempfile.mkdtemp(prefix="aav-files-")
os.environ["AAV_MAX_UPLOAD_BYTES"] = str(2 * 1024 * 1024)
os.environ["AAV_TENANT_QUOTA_BYTES"] = str(5 * 1024 * 1024)
os.environ["AAV_EGRESS_ALLOWLIST"] = "example.com,localhost"
# Existing end-to-end tests exercise real response paths; harness tests set SIMULATION/OBSERVE per tenant.
os.environ["AAV_HARNESS_DEFAULT_MODE"] = "respond"
sys.path.insert(0, str(PRODUCT / "detection"))
sys.path.insert(0, str(CP))


def _dsn_for(dbname: str, user: str | None = None) -> str:
    base = psycopg.conninfo.conninfo_to_dict(ADMIN_DSN)
    base["dbname"] = dbname
    if user:
        base["user"] = user
        if user == "aav_app":
            base["password"] = APP_PASSWORD
    return psycopg.conninfo.make_conninfo(**base)


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f"CREATE DATABASE {DB_NAME}")
    admin = _dsn_for(DB_NAME)
    with psycopg.connect(admin, autocommit=True) as c:
        for f in sorted((CP / "migrations").glob("*.sql")):
            c.execute(f.read_text())
        c.execute(f"ALTER ROLE aav_app PASSWORD '{APP_PASSWORD}'")
    from app import crypto, db
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    db.set_dsn(_dsn_for(DB_NAME, "aav_app"))
    crypto.set_signing_key(Ed25519PrivateKey.generate())
    yield admin
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")


@pytest.fixture(scope="session", autouse=True)
def aepx_governance():
    env = dict(os.environ, DATABASE_URL="postgresql://nobody@127.0.0.1:1/none")
    proc = subprocess.Popen([os.environ.get("AAV_GOVERNANCE_PYTHON", sys.executable), "-m", "uvicorn", "app.main:app", "--port", str(GOV_PORT)],
                            cwd=REPO / "services" / "governance", env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    import httpx
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{GOV_PORT}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("AEP-X governance did not start")
    yield f"http://127.0.0.1:{GOV_PORT}"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def admin_sql(database):
    def run(sql, *args):
        with psycopg.connect(database, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
            cur = c.execute(sql, args)
            return cur.fetchall() if cur.description else None
    return run


@pytest.fixture(scope="session")
def client(database, aepx_governance):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _last_token(admin_sql, email: str, template: str) -> str:
    rows = admin_sql("SELECT payload FROM aav.outbound_mail WHERE to_email = %s AND template = %s "
                     "ORDER BY created_at DESC LIMIT 1", email, template)
    return rows[0]["payload"]["link"].split("token=")[1]


class Account:
    def __init__(self, client, email, token, tenant_id, user_id):
        self.client, self.email, self.token, self.tenant_id, self.user_id = client, email, token, tenant_id, user_id

    @property
    def h(self):
        return {"Authorization": f"Bearer {self.token}", "X-Tenant-Id": self.tenant_id}

    def get(self, path, **kw):
        return self.client.get(path, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def post(self, path, **kw):
        return self.client.post(path, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def put(self, path, **kw):
        return self.client.put(path, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def patch(self, path, **kw):
        return self.client.patch(path, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def delete(self, path, **kw):
        return self.client.delete(path, headers={**self.h, **kw.pop("headers", {})}, **kw)


@pytest.fixture(scope="session")
def new_account(client, admin_sql):
    def make(prefix="admin") -> Account:
        email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
        r = client.post("/v1/auth/register", json={"email": email, "password": "correct horse battery",
                                                   "organisation": f"Org {prefix}"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert client.post("/v1/auth/verify-email",
                           json={"token": _last_token(admin_sql, email, "verify-email")}).status_code == 200
        tok = client.post("/v1/auth/login", json={"email": email, "password": "correct horse battery"}).json()
        return Account(client, email, tok["access_token"], body["tenant_id"], body["user_id"])
    return make


@pytest.fixture(scope="session")
def invite(client, admin_sql):
    def make(admin: Account, role: str) -> Account:
        email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
        r = admin.post("/v1/auth/invitations", json={"email": email, "role": role})
        assert r.status_code == 201, r.text
        tok = client.post("/v1/auth/invitations/accept", json={
            "token": _last_token(admin_sql, email, "accept-invite"), "password": "another long password"}).json()
        return Account(client, email, tok["access_token"], admin.tenant_id, r.json()["user_id"])
    return make


@pytest.fixture(scope="session")
def baseline_bundle(new_account):
    """Publish the shipped baseline detection bundle once (signed by the control plane)."""
    ops = new_account("operator")
    data = json.loads((PRODUCT / "detection" / "rules" / "baseline.json").read_text())
    r = ops.post("/v1/updates", json={"kind": "detections", "version": data["version"], "body": data["body"]})
    assert r.status_code in (201, 409), r.text
    return data


def eicar() -> bytes:
    # Assembled at runtime so the repository itself never contains the test string.
    parts = ["X5O!P%@AP[4\\PZX54(P^)7CC)7}", "$EICAR-STANDARD-", "ANTIVIRUS-TEST-FILE!$H+H*"]
    return "".join(parts).encode()


@pytest.fixture(scope="session")
def enrol(client):
    def make(admin: Account, hostname="host-1", os_name="windows"):
        if not admin.get("/v1/policies").json():
            r = admin.post("/v1/policies", json={"name": "default", "body": {
                "on_access": True, "on_execute": True, "on_download": True, "auto_quarantine_known": True,
                "behaviour_rules": True, "event_buffer_mb": 64, "isolation_allowed": True,
                "allowed_management_hosts": ["console.example.com"], "tamper_protection": True}})
            assert r.status_code == 201, r.text
        tok = admin.post("/v1/enrollment-tokens", json={"max_uses": 5}).json()["token"]
        r = client.post("/v1/agent/enrol", json={"token": tok, "hostname": hostname, "os": os_name,
                                                 "os_version": "11", "agent_version": "0.1.0"})
        assert r.status_code == 201, r.text
        return r.json()
    return make
