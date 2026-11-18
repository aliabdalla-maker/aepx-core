"""FN-01, FN-02, BE-03, AX-12 cross-tenant isolation, KPI-05 failed logins, USR-04, USR-05."""
import uuid

import psycopg
import pytest

from conftest import _dsn_for, DB_NAME, _last_token


def test_register_verify_login_logout(client, admin_sql):
    email = f"u-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/v1/auth/register", json={"email": email, "password": "short", "organisation": "X"})
    assert r.status_code == 422  # password policy
    r = client.post("/v1/auth/register", json={"email": email, "password": "a sufficiently long pw",
                                               "organisation": "Acme"})
    assert r.status_code == 201
    tenant = r.json()["tenant_id"]
    assert client.post("/v1/auth/register", json={"email": email, "password": "a sufficiently long pw",
                                                  "organisation": "Acme"}).status_code == 409
    tok = client.post("/v1/auth/login", json={"email": email, "password": "a sufficiently long pw"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}", "X-Tenant-Id": tenant}
    assert client.get("/v1/devices", headers=h).status_code == 403  # email not verified yet
    assert client.post("/v1/auth/verify-email", json={"token": _last_token(admin_sql, email, "verify-email")}).json() == \
        {"verified": True}
    assert client.get("/v1/devices", headers=h).status_code == 200
    me = client.get("/v1/auth/me", headers=h).json()
    assert me["tenants"][0]["roles"] == ["tenant_admin"]
    assert client.post("/v1/auth/logout", headers=h).json() == {"logged_out": True}
    assert client.get("/v1/devices", headers=h).status_code == 401


def test_lockout_and_failed_login_audit(client, new_account, admin_sql):
    a = new_account("lock")
    for _ in range(5):
        assert client.post("/v1/auth/login", json={"email": a.email, "password": "wrong password!!"}).status_code == 401
    assert client.post("/v1/auth/login", json={"email": a.email, "password": "correct horse battery"}).status_code == 423
    n = admin_sql("SELECT count(*) AS n FROM aav.audit_log WHERE action = 'auth.login_failed' AND target = %s", a.email)
    assert n[0]["n"] == 5


def test_password_reset_revokes_sessions(client, new_account, admin_sql):
    a = new_account("reset")
    assert client.post("/v1/auth/password-reset/request", json={"email": a.email}).status_code == 200
    token = _last_token(admin_sql, a.email, "reset-password")
    assert client.post("/v1/auth/password-reset/confirm", json={"token": token, "new_password": "brand new password"}
                       ).json() == {"reset": True}
    assert client.post("/v1/auth/password-reset/confirm", json={"token": token, "new_password": "brand new password"}
                       ).status_code == 400  # single use
    assert a.get("/v1/devices").status_code == 401
    assert client.post("/v1/auth/login", json={"email": a.email, "password": "brand new password"}).status_code == 200


def test_profile_and_delete_account(client, new_account, invite):
    a = new_account("prof")
    analyst = invite(a, "security_analyst")
    assert analyst.client.patch("/v1/auth/me", headers=analyst.h, json={"locale": "ar", "display_name": "Sam"}).status_code == 200
    assert analyst.client.patch("/v1/auth/me", headers=analyst.h, json={"locale": "xx"}).status_code == 422
    assert analyst.client.delete("/v1/auth/me", headers=analyst.h).json() == {"deleted": True}
    assert analyst.get("/v1/alerts").status_code == 401
    assert all(m["user_id"] != analyst.user_id for m in a.get("/v1/members").json())


def test_roles_least_privilege(new_account, invite):
    a = new_account("roles")
    auditor = invite(a, "auditor")
    user = invite(a, "endpoint_user")
    assert auditor.get("/v1/audit").status_code == 200
    assert auditor.post("/v1/policies", json={"name": "x", "body": {}}).status_code == 403
    assert auditor.post("/v1/actions", json={"action_type": "run_scan", "targets": [str(uuid.uuid4())],
                                             "params": {"scan_type": "quick"}}).status_code == 403
    assert user.get("/v1/audit").status_code == 403
    assert user.get("/v1/devices").status_code == 200  # own devices only
    assert user.post("/v1/enrollment-tokens", json={}).status_code == 403


def test_cross_tenant_requests_are_denied(new_account, enrol):
    a, b = new_account("ta"), new_account("tb")
    dev_b = enrol(b, "b-host")
    # A presenting B's tenant id: not a member -> indistinguishable from a missing tenant
    assert a.client.get("/v1/devices", headers={**a.h, "X-Tenant-Id": b.tenant_id}).status_code == 404
    # A targeting B's device through its own tenant: target not found, nothing dispatched
    r = a.post("/v1/actions", json={"action_type": "isolate_device", "targets": [dev_b["device_id"]],
                                    "params": {"expires_minutes": 30}})
    assert r.status_code == 404
    assert all(d["id"] != dev_b["device_id"] for d in a.get("/v1/devices").json())


def test_rls_enforced_at_database_level(new_account, enrol):
    a, b = new_account("rla"), new_account("rlb")
    enrol(a, "a-host")
    enrol(b, "b-host")
    with psycopg.connect(_dsn_for(DB_NAME, "aav_app")) as c:
        assert c.execute("SELECT count(*) FROM aav.devices").fetchone()[0] == 0  # no tenant context -> nothing
        c.execute("SELECT set_config('aav.tenant_id', %s, false)", (a.tenant_id,))
        rows = c.execute("SELECT DISTINCT tenant_id::text FROM aav.devices").fetchall()
        assert rows == [(a.tenant_id,)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO aav.incidents (tenant_id, title, severity) VALUES (%s, 'x', 'low')", (b.tenant_id,))


def test_msp_child_tenant_independent(new_account):
    msp = new_account("msp")
    child = msp.post("/v1/tenants", json={"name": "Customer 1"}).json()["tenant_id"]
    roles = {t["tenant_id"]: t["roles"] for t in msp.get("/v1/auth/me").json()["tenants"]}
    assert set(roles[child]) == {"tenant_admin", "msp_operator"}
    as_child = {**msp.h, "X-Tenant-Id": child}
    assert msp.client.get("/v1/policies", headers=as_child).json() == []
    assert msp.client.get("/v1/audit", headers=as_child).json()[0]["action"] == "tenant.create_child"


def test_invitation_only_mode_blocks_registration(client, monkeypatch):
    from app.routers import auth
    import dataclasses
    monkeypatch.setattr(auth, "settings", dataclasses.replace(auth.settings, allow_open_registration=False))
    r = client.post("/v1/auth/register", json={"email": "x@example.com", "password": "long enough password",
                                               "organisation": "X"})
    assert r.status_code == 403
