"""AGT-03/04 agent memory with access-controlled retrieval, and KPI-01 business KPIs."""
import pytest

from app.config import settings


@pytest.fixture(scope="module")
def team(new_account, invite):
    admin = new_account("mem")
    return admin, invite(admin, "security_analyst"), invite(admin, "auditor"), invite(admin, "endpoint_user")


def note(acct, **kw):
    body = {"kind": "finding", "title": "LSASS dump via comsvcs", "source_kind": "incident", "source_ref": "inc-42",
            "content": "rundll32 comsvcs.dll MiniDump against lsass on finance-lt; contained by isolation."}
    body.update(kw)
    return acct.post("/v1/memory", json=body)


def test_retrieval_returns_cited_passages_and_respects_permissions(team):
    admin, analyst, auditor, user = team
    r = note(analyst)
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    secret = note(admin, title="Payroll export runbook", content="payroll lsass escalation contacts",
                  kind="runbook", source_kind="user", required_permission="audit.read")
    assert secret.status_code == 201
    hits = analyst.post("/v1/memory/retrieve", json={"query": "lsass comsvcs"}).json()["passages"]
    assert [h["title"] for h in hits] == ["LSASS dump via comsvcs"]     # analyst lacks audit.read
    c = hits[0]["citation"]
    assert c["memory_key"] == key and c["source"] == "incident:inc-42" and c["version"] == 1
    assert c["created_by"].startswith("user:")
    assert {h["title"] for h in auditor.post("/v1/memory/retrieve", json={"query": "lsass"}).json()["passages"]} == \
        {"LSASS dump via comsvcs", "Payroll export runbook"}
    assert user.get("/v1/memory/search", params={"q": "lsass"}).status_code == 403   # no memory.read
    assert auditor.post("/v1/memory", json={"kind": "finding", "title": "x", "content": "y",
                                            "source_kind": "user"}).status_code == 403
    assert analyst.get(f"/v1/memory/{secret.json()['key']}").status_code == 404
    escalate = note(analyst, required_permission="billing.manage")
    assert escalate.status_code == 403                                   # cannot restrict above own rights


def test_versioning_consent_and_erasure(team, admin_sql):
    admin, analyst, *_ = team
    assert note(analyst, contains_personal_data=True).status_code == 422
    r = note(analyst, title="Phish from contractor", content="user jane reported phishing mail",
             contains_personal_data=True, consent_basis="legitimate_interest_security", retain_days=30).json()
    key = r["key"]
    v2 = analyst.put(f"/v1/memory/{key}", json={"kind": "finding", "title": "Phish from contractor",
                                                "content": "reported phishing mail; sender domain blocked",
                                                "source_kind": "alert", "source_ref": "al-7",
                                                "contains_personal_data": False}).json()
    assert v2["version"] == 2
    vers = analyst.get(f"/v1/memory/{key}/versions").json()
    assert [v["version"] for v in vers] == [2, 1] and vers[1]["superseded_at"] is not None
    hits = analyst.get("/v1/memory/search", params={"q": "phishing"}).json()["passages"]
    assert [h["citation"]["version"] for h in hits if h["citation"]["memory_key"] == key] == [2]
    assert admin.delete(f"/v1/memory/{key}").json() == {"erased_versions": 2}
    assert analyst.get(f"/v1/memory/{key}").status_code == 404
    assert any(e["action"] == "memory.erase" for e in admin.get("/v1/audit").json())


def test_retention_deletes_expired_items(team, admin_sql):
    _, analyst, *_ = team
    key = note(analyst, title="Short-lived", content="temporary retention probe", retain_days=1).json()["key"]
    admin_sql("UPDATE aav.memory_items SET retain_until = now() - interval '1 minute' WHERE key = %s", key)
    assert admin_sql("SELECT aav.apply_memory_retention() AS n")[0]["n"] >= 1
    assert analyst.get(f"/v1/memory/{key}").status_code == 404


def test_memory_is_tenant_isolated(team, new_account):
    _, analyst, *_ = team
    other = new_account("mem-other")
    note(other, title="Other tenant secret", content="lsass other tenant")
    titles = {h["title"] for h in analyst.post("/v1/memory/retrieve", json={"query": "lsass"}).json()["passages"]}
    assert "Other tenant secret" not in titles


def test_business_kpis_for_platform_operators_only(new_account, enrol):
    op = new_account("op")
    assert op.client.get("/v1/platform/business-kpis", headers={"Authorization": f"Bearer {op.token}"}).status_code == 403
    enrol(op, hostname="kpi-host")
    object.__setattr__(settings, "platform_operators", frozenset({op.email.lower()}))
    try:
        k = op.client.get("/v1/platform/business-kpis", headers={"Authorization": f"Bearer {op.token}"}).json()
    finally:
        object.__setattr__(settings, "platform_operators", frozenset())
    assert k["tenants"] >= 1 and k["active_users_30d"] >= 1
    assert 0 < k["activation_rate"] <= 1
    assert set(k["feature_adoption"]) >= {"endpoint_protection", "response_actions", "memory", "files"}
    assert k["feature_adoption"]["endpoint_protection"] > 0
    assert "tenant_id" not in str(k)                                      # aggregates only
