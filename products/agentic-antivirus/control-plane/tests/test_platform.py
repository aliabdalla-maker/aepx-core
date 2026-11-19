"""SET-01..06, L10N-01..12, KPI/DSH, audit integrity, OpenAPI, readiness."""
import psycopg
import pytest


def test_settings_schema_validation_rbac_history_rollback(new_account, invite):
    admin = new_account("set")
    it = invite(admin, "it_admin")
    assert len(admin.get("/v1/settings/schema").json()) == 19
    assert it.put("/v1/settings/appearance/theme", json={"value": "dark"}).json()["version"] == 1
    assert it.put("/v1/settings/appearance/theme", json={"value": "neon"}).status_code == 422
    assert it.put("/v1/settings/appearance/unknown", json={"value": 1}).status_code == 404
    assert it.put("/v1/settings/privacy/collect_file_contents", json={"value": True}).status_code == 403  # sensitive
    assert admin.put("/v1/settings/privacy/collect_file_contents", json={"value": True}).status_code == 200
    assert admin.put("/v1/settings/storage/quota_bytes", json={"value": "lots"}).status_code == 422
    it.put("/v1/settings/appearance/theme", json={"value": "high_contrast"})
    hist = it.get("/v1/settings/appearance/theme/history").json()
    assert [h["version"] for h in hist] == [2, 1]
    assert it.post("/v1/settings/appearance/theme/rollback/1").json()["version"] == 3
    assert next(s for s in it.get("/v1/settings").json() if s["key"] == "theme")["value"] == "dark"
    assert it.delete("/v1/settings/appearance/theme").json() == {"deleted": True}


def test_locale_catalogue_coverage_and_fallback(client):
    locs = client.get("/v1/i18n/locales").json()
    assert len(locs) == 100
    by = {loc["locale"]: loc for loc in locs}
    assert by["en"]["status"] == "complete" and by["en"]["coverage_pct"] == 100.0
    assert {k for k, v in by.items() if v["direction"] == "rtl"} == {"ar", "fa", "he", "ps", "ur", "yi"}
    assert by["zh-Hans"]["fallback_chain"] == ["zh-Hans", "zh", "en"]
    unavailable = [k for k, v in by.items() if v["status"] == "unavailable"]
    assert len(unavailable) == 99  # reported honestly: only English is translated in this release
    m = client.get("/v1/i18n/messages/ar").json()
    assert m["direction"] == "rtl" and m["messages"]["nav.devices"] == "Devices"  # English fallback
    assert client.get("/v1/i18n/messages/xx").status_code == 404


def test_kpis_live_and_exports(new_account):
    a = new_account("kpi")
    k = a.get("/v1/kpis").json()
    assert k["freshness"]["source"] == "live database queries" and k["devices"]["enrolled"] == 0
    assert a.get("/v1/kpis/export", params={"fmt": "csv"}).text.startswith("group,metric,value")
    pdf = a.get("/v1/kpis/export", params={"fmt": "pdf"})
    assert pdf.content.startswith(b"%PDF-1.4") and pdf.content.rstrip().endswith(b"%%EOF")
    assert a.get("/v1/kpis/export", params={"fmt": "json"}).json()["devices"]["enrolled"] == 0


def test_audit_chain_verifies_and_is_append_only(new_account, admin_sql, database):
    a = new_account("aud")
    a.put("/v1/settings/appearance/theme", json={"value": "light"})
    v = a.get("/v1/audit/verify").json()
    assert v["valid"] is True and v["entries"] >= 2
    with pytest.raises(psycopg.errors.RaiseException):
        admin_sql("UPDATE aav.audit_log SET actor = 'x' WHERE tenant_id = %s", a.tenant_id)
    with pytest.raises(psycopg.errors.RaiseException):
        admin_sql("DELETE FROM aav.audit_log WHERE tenant_id = %s", a.tenant_id)
    # A superuser bypassing the trigger is still detected by the chain check
    admin_sql("ALTER TABLE aav.audit_log DISABLE TRIGGER audit_no_update")
    try:
        admin_sql("UPDATE aav.audit_log SET detail = '{\"tampered\": true}' WHERE id = (SELECT max(id) FROM "
                  "aav.audit_log WHERE tenant_id = %s)", a.tenant_id)
    finally:
        admin_sql("ALTER TABLE aav.audit_log ENABLE TRIGGER audit_no_update")
    assert a.get("/v1/audit/verify").json()["valid"] is False


def test_members_cannot_remove_last_admin(new_account, invite):
    a = new_account("mem")
    u = invite(a, "auditor")
    assert a.post("/v1/members", json={"user_id": u.user_id, "role": "security_analyst"}).json() == {"ok": True}
    assert a.delete(f"/v1/members/{a.user_id}/tenant_admin").status_code == 409


def test_openapi_and_readiness(client):
    spec = client.get("/v1/openapi.json").json()
    assert spec["info"]["title"] == "Agentic Antivirus Control Plane" and len(spec["paths"]) > 90
    r = client.get("/ready").json()
    assert r["checks"]["database"] is True and r["checks"]["aepx_governance"] is True
    assert r["ready"] is True
