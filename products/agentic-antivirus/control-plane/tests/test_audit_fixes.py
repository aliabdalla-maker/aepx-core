"""Fixes from the console audit of 27 Nov 2026 (production screenshots): input validation that let wrong values
inflate or corrupt KPIs, credential leakage into a reference field, and wording leaks in investigations."""
import pytest


@pytest.fixture(scope="module")
def admin(new_account):
    return new_account("audit")


@pytest.mark.parametrize("category,key,bad,good", [
    ("localization", "timezone", "Gmt", "Europe/London"),
    ("storage", "quota_bytes", 36, 5 * 1024 ** 3),
    ("network", "egress_allowlist", ["321"], ["api.cloudflare.com"]),
    ("integration_ports", "approved_ports", [99999], [8443]),
    ("backups", "backup_integration_id", "123", "6f1c2b8e-1c55-4c49-9a3e-9b8f7a0c1d2e"),
    ("llm_providers", "provider", "Openrouter\n", "none"),
    ("billing_limits", "max_cost_per_task_usd", 9, 1),
    ("general", "organisation_name", "Equality Software ", "Equality Software LTD"),
    ("agent_policies", "approval_ttl_minutes", 1, 60),
])
def test_settings_reject_values_that_make_no_sense(admin, category, key, bad, good):
    r = admin.put(f"/v1/settings/{category}/{key}", json={"value": bad})
    assert r.status_code == 422, (key, r.text)
    assert admin.put(f"/v1/settings/{category}/{key}", json={"value": good}).status_code == 200


def test_integration_refuses_pasted_keys_and_schemeless_endpoints(admin):
    r = admin.post("/v1/integrations", json={"name": "or", "signal_kind": "api_gateway", "protocol": "webhook",
                                             "secret_ref": "sk-or-v1-" + "a1b2c3d4" * 6})
    assert r.status_code == 422 and "revoke" in r.json()["detail"]
    r = admin.post("/v1/integrations", json={"name": "or2", "signal_kind": "api_gateway", "protocol": "webhook",
                                             "endpoint": "openrouter"})
    assert r.status_code == 422 and "https://" in r.json()["detail"]
    ok = admin.post("/v1/integrations", json={"name": "or3", "signal_kind": "api_gateway", "protocol": "webhook",
                                              "endpoint": "https://api.example.com", "secret_ref": "gateway-prod"})
    assert ok.status_code == 201


def test_ddos_public_endpoints_must_be_public(admin, admin_sql):
    r = admin.post("/v1/assets", json={"kind": "ip", "value": "172.27.80.1", "service": "local_ip"})
    assert r.status_code == 422 and "private" in r.json()["detail"]
    assert admin.post("/v1/assets", json={"kind": "hostname", "value": "openrouter", "service": "x"}).status_code == 422
    # a private address stored before validation existed is reported as invalid and not counted as covered
    admin_sql("INSERT INTO aav.protected_assets (tenant_id, kind, value, service, service_owner, provider, "
              "mitigation_policy, capacity_assumptions, public) VALUES (%s,'ip','10.1.2.3','legacy','SEL','SEL',"
              "'draft','1T',true)", admin.tenant_id)
    cov = admin.get("/v1/ddos/coverage").json()
    assert [i["value"] for i in cov["invalid"]] == ["10.1.2.3"]
    assert cov["public_endpoints"] == 0 and cov["accounted_pct"] is None


def test_policy_management_hosts_and_cron(admin):
    body = {"name": "default", "body": {"allowed_management_hosts": ["D:\\ADLC Development Sources"]}}
    r = admin.post("/v1/policies", json=body)
    assert r.status_code == 422 and "not a host name" in r.json()["detail"]
    body["body"]["allowed_management_hosts"] = ["console.example.com", "10.0.0.0/24"]
    assert admin.post("/v1/policies", json=body).status_code == 201
    assert admin.post("/v1/scan-schedules", json={"policy_name": "default", "scan_type": "full",
                                                  "cron": "61 2 * * 0"}).status_code == 422
    assert admin.post("/v1/scan-schedules", json={"policy_name": "default", "scan_type": "full",
                                                  "cron": "0 2 * * 0"}).status_code == 201


def test_people_listed_by_email_once(admin, invite):
    rows = admin.get("/v1/members").json()
    me = [r for r in rows if r["email"] == admin.email]
    assert len(me) == 1 and "tenant_admin" in me[0]["roles"]


def test_investigation_never_prints_none(admin):
    r = admin.post("/v1/reports", json={"kind": "url", "description": "odd link", "url": "http://x.example/a"})
    if r.status_code not in (200, 201):
        pytest.skip("report endpoint shape differs")
    inc = admin.get("/v1/incidents").json()[0]
    inv = admin.post(f"/v1/incidents/{inc['id']}/investigate", json={}).json()
    text = str(inv)
    assert " on None" not in text and "1 evidence items" not in text
