"""Settings, locales, KPIs, audit, tenants (MSP) and members.

Trace: SET-01..06, L10N-*, KPI-01..08, DSH-01..07, FN-02, FN-04, USR-04 (MSP), USR-05 (auditor),
OBJ-04/OBJ-07 measurement, RA-15/16.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import audit, db, i18n, rbac
from app.deps import Principal, current_user, need

router = APIRouter(prefix="/v1", tags=["platform"])

# Category -> key -> (type, sensitive). Secrets are never stored here: only references.
SETTINGS_SCHEMA: dict[str, dict[str, tuple[type, bool]]] = {
    "general": {"organisation_name": (str, False), "support_email": (str, False)},
    "localization": {"default_locale": (str, False), "timezone": (str, False)},
    "voice": {"tts_enabled": (bool, False), "stt_enabled": (bool, False), "voice_retention_days": (int, True)},
    "appearance": {"theme": (str, False)},
    "accessibility": {"reduced_motion": (bool, False), "font_scale": (float, False)},
    "users": {"invite_only": (bool, True)},
    "roles": {"require_two_approvers_for_bulk": (bool, True)},
    "authentication": {"oidc_enabled": (bool, True), "google_login": (bool, True), "session_hours": (int, True)},
    "privacy": {"collect_file_contents": (bool, True), "telemetry_retention_days": (int, True),
                "evidence_retention_days": (int, True)},
    "storage": {"quota_bytes": (int, True)},
    "backups": {"backup_integration_id": (str, True)},
    "network": {"egress_allowlist": (list, True)},
    "integration_ports": {"approved_ports": (list, True)},
    "agent_policies": {"auto_quarantine_known": (bool, True), "approval_ttl_minutes": (int, True)},
    "llm_providers": {"enabled": (bool, True), "provider": (str, True)},
    "notifications": {"email_critical": (bool, False), "digest": (str, False)},
    "telemetry": {"otel_enabled": (bool, True)},
    "billing_limits": {"max_cost_per_task_usd": (float, True), "monthly_budget_usd": (float, True)},
    "updates": {"channel": (str, True), "auto_update_definitions": (bool, True)},
}
ENUMS = {("appearance", "theme"): {"light", "dark", "high_contrast", "system"},
         ("updates", "channel"): {"stable", "beta"},
         ("notifications", "digest"): {"none", "daily", "weekly"}}


class SettingIn(BaseModel):
    value: object


class TenantIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberRoleIn(BaseModel):
    user_id: UUID
    role: str


def _validate_setting(category: str, key: str, value) -> None:
    spec = SETTINGS_SCHEMA.get(category, {}).get(key)
    if not spec:
        raise HTTPException(404, "unknown setting")
    t = spec[0]
    ok = isinstance(value, t) and not (t in (int, float) and isinstance(value, bool))
    if t is float and isinstance(value, int) and not isinstance(value, bool):
        ok = True
    if not ok:
        raise HTTPException(422, f"{category}.{key} must be {t.__name__}")
    if (category, key) in ENUMS and value not in ENUMS[(category, key)]:
        raise HTTPException(422, f"{category}.{key} must be one of {sorted(ENUMS[(category, key)])}")
    if (category, key) == ("localization", "default_locale") and value not in i18n.LOCALES:
        raise HTTPException(422, "unsupported locale")
    rule = RULES.get((category, key))
    if rule:
        msg = rule(value)
        if msg:
            raise HTTPException(422, f"{category}.{key}: {msg}")


def _range(lo, hi, unit=""):
    return lambda v: None if lo <= v <= hi else f"must be between {lo} and {hi}{unit}"


def _tz(v):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(v)
        return None if "/" in v or v == "UTC" else "use an IANA time zone such as Europe/London or UTC"
    except (ZoneInfoNotFoundError, ValueError):
        return "use an IANA time zone such as Europe/London or UTC"


_HOST = __import__("re").compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _hosts(v):
    bad = [h for h in v if not isinstance(h, str) or not _HOST.match(h.strip().lower())]
    return f"not hostnames: {bad[:5]}" if bad else None


def _ports(v):
    bad = [x for x in v if not (isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 65535)
           and not (isinstance(x, str) and x.isdigit() and 1 <= int(x) <= 65535)]
    return f"not TCP ports: {bad[:5]}" if bad else None


def _uuid_or_empty(v):
    try:
        UUID(v)
        return None
    except ValueError:
        return None if v == "" else "must be the id of a backup integration (a UUID)"


def _clean_text(maxlen):
    return lambda v: ("must not start or end with spaces or contain line breaks"
                      if v != v.strip() or "\n" in v or "\r" in v else
                      (f"must be at most {maxlen} characters" if len(v) > maxlen else
                       ("must not be empty" if not v else None)))


def _email(v):
    return None if __import__("re").fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", v) else "must be an email address"


# Value rules beyond the type (audit 27 Nov 2026: settings accepted "Gmt", 36-byte quotas, "321" as an egress host).
RULES = {
    ("general", "organisation_name"): _clean_text(200),
    ("general", "support_email"): _email,
    ("localization", "timezone"): _tz,
    ("voice", "voice_retention_days"): _range(0, 365, " days"),
    ("accessibility", "font_scale"): _range(0.75, 2.0),
    ("authentication", "session_hours"): _range(1, 24 * 30, " hours"),
    ("privacy", "telemetry_retention_days"): _range(7, 3650, " days"),
    ("privacy", "evidence_retention_days"): _range(30, 3650, " days"),
    ("storage", "quota_bytes"): _range(10 * 1024 * 1024, 10 * 1024 ** 4, " bytes (10 MB to 10 TB)"),
    ("backups", "backup_integration_id"): _uuid_or_empty,
    ("network", "egress_allowlist"): _hosts,
    ("integration_ports", "approved_ports"): _ports,
    ("agent_policies", "approval_ttl_minutes"): _range(5, 7 * 24 * 60, " minutes"),
    ("llm_providers", "provider"): lambda v: None if v in ("anthropic", "ollama", "none")
    else "must be one of anthropic, ollama, none (D-07: none in Release 1)",
    ("billing_limits", "max_cost_per_task_usd"): _range(0, 1.0, " USD (owner decision D-09 caps a task at 1.00)"),
    ("billing_limits", "monthly_budget_usd"): _range(0, 10000, " USD"),
}


@router.get("/settings/schema")
def settings_schema(p: Principal = Depends(need("settings.read"))):
    return {c: {k: {"type": t.__name__, "sensitive": s, "enum": sorted(ENUMS.get((c, k), [])) or None}
                for k, (t, s) in keys.items()} for c, keys in SETTINGS_SCHEMA.items()}


@router.get("/settings")
def get_settings(p: Principal = Depends(need("settings.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT category, key, value, version, updated_at FROM aav.settings ORDER BY category, key")
        return cur.fetchall()


@router.put("/settings/{category}/{key}")
def put_setting(category: str, key: str, body: SettingIn, p: Principal = Depends(need("settings.write"))):
    _validate_setting(category, key, body.value)
    if SETTINGS_SCHEMA[category][key][1]:
        p.require("settings.write_sensitive")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.settings (tenant_id, category, key, value, updated_by) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id, category, key) DO UPDATE SET value = EXCLUDED.value, version = "
                    "aav.settings.version + 1, updated_by = EXCLUDED.updated_by, updated_at = now() RETURNING version",
                    (p.tenant_id, category, key, json.dumps(body.value), p.user_id))
        v = cur.fetchone()["version"]
        cur.execute("INSERT INTO aav.settings_history (tenant_id, category, key, version, value, changed_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", (p.tenant_id, category, key, v, json.dumps(body.value), p.user_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="settings.update", target=f"{category}.{key}",
                     detail={"version": v, "value": body.value})
    return {"version": v}


@router.delete("/settings/{category}/{key}")
def delete_setting(category: str, key: str, p: Principal = Depends(need("settings.write"))):
    if SETTINGS_SCHEMA.get(category, {}).get(key, (None, False))[1]:
        p.require("settings.write_sensitive")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("DELETE FROM aav.settings WHERE category = %s AND key = %s RETURNING version", (category, key))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not set")
        cur.execute("INSERT INTO aav.settings_history (tenant_id, category, key, version, value, changed_by) "
                    "VALUES (%s,%s,%s,%s,NULL,%s)", (p.tenant_id, category, key, row["version"] + 1, p.user_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="settings.delete", target=f"{category}.{key}")
    return {"deleted": True}


@router.get("/settings/{category}/{key}/history")
def setting_history(category: str, key: str, p: Principal = Depends(need("settings.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT version, value, changed_by, changed_at FROM aav.settings_history WHERE category = %s "
                    "AND key = %s ORDER BY version DESC", (category, key))
        return cur.fetchall()


@router.post("/settings/{category}/{key}/rollback/{version}")
def rollback_setting(category: str, key: str, version: int, p: Principal = Depends(need("settings.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT value FROM aav.settings_history WHERE category = %s AND key = %s AND version = %s",
                    (category, key, version))
        row = cur.fetchone()
    if not row or row["value"] is None:
        raise HTTPException(404, "version not found")
    return put_setting(category, key, SettingIn(value=row["value"]), p)


def _db_translations(locale: str | None = None) -> list[dict]:
    with db.global_tx() as cur:
        cur.execute("SELECT locale, msg_key, source_hash, text, origin FROM aav.translations "
                    "WHERE %s::text IS NULL OR locale = %s", (locale, locale))
        return cur.fetchall()


def _src_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@router.get("/i18n/locales")
def locales():
    """Per-locale coverage with provenance: human (reviewed) vs machine translated (L10N-11/12)."""
    base = i18n.base_messages()
    rows: dict = {}
    for t in _db_translations():
        if t["msg_key"] in base and t["source_hash"] == _src_hash(base[t["msg_key"]]):
            rows.setdefault(t["locale"], {})[t["msg_key"]] = t["origin"]
    out = []
    for c in i18n.coverage():
        loc = c["locale"]
        meta = i18n.file_meta(loc)
        file_keys = set(i18n.file_messages(loc)) & set(base)
        machine_file = set() if loc == i18n.FALLBACK or meta.get("origin", "human") == "human" else \
            file_keys - set(meta.get("reviewed_keys", []))
        db_keys = rows.get(loc, {})
        keys = file_keys | set(db_keys)
        machine = machine_file | {k for k, o in db_keys.items() if o != "human" and k not in file_keys}
        total = len(base)
        out.append({**c, "keys_translated": len(keys), "keys_machine": len(machine),
                    "keys_reviewed": len(keys - machine),
                    "coverage_pct": round(100 * len(keys) / total, 1) if total else 0.0,
                    "reviewed_pct": round(100 * len(keys - machine) / total, 1) if total else 0.0,
                    "status": "complete" if total and len(keys) == total else ("partial" if keys else "unavailable"),
                    "label": "machine translated, not yet reviewed" if machine else None})
    return out


@router.get("/i18n/messages/{locale}")
def messages(locale: str):
    if locale not in i18n.LOCALES:
        raise HTTPException(404, "unsupported locale")
    base = i18n.base_messages()
    merged: dict = {}
    machine: set = set()
    for loc in reversed(i18n.fallback_chain(locale)):
        msgs = i18n.file_messages(loc)
        merged.update(msgs)
        meta = i18n.file_meta(loc)
        if loc != i18n.FALLBACK and meta.get("origin", "human") != "human":
            machine |= set(msgs) - set(meta.get("reviewed_keys", []))
        for t in _db_translations(loc):
            if t["msg_key"] in base and t["msg_key"] not in msgs and t["source_hash"] == _src_hash(base[t["msg_key"]]):
                merged[t["msg_key"]] = t["text"]
                if t["origin"] != "human":
                    machine.add(t["msg_key"])
    machine &= set(merged)
    return {"locale": locale, "direction": "rtl" if locale in i18n.RTL else "ltr", "messages": merged,
            "machine_translated": sorted(machine),
            "label": "machine translated, not yet reviewed" if machine else None}


@router.get("/audit")
def audit_log(limit: int = 200, offset: int = 0, action: str | None = None, p: Principal = Depends(need("audit.read"))):
    limit = max(1, min(limit, 1000))
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT id, actor, action, target, detail, trace_id, at, hash FROM aav.audit_log "
                    "WHERE (%s::text IS NULL OR action = %s) ORDER BY id DESC LIMIT %s OFFSET %s",
                    (action, action, limit, offset))
        return cur.fetchall()


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(need("audit.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        return audit.verify_chain(cur)


def _kpis(cur) -> dict:
    now = datetime.now(timezone.utc)
    q = {}

    def one(sql, *args):
        cur.execute(sql, args)
        return cur.fetchone()

    q["devices"] = one("SELECT count(*) FILTER (WHERE retired_at IS NULL) AS enrolled, count(*) FILTER (WHERE "
                       "protection_status = 'protected' AND retired_at IS NULL) AS protected, count(*) FILTER (WHERE "
                       "last_seen_at > now() - interval '30 minutes' AND retired_at IS NULL) AS reporting, count(*) "
                       "FILTER (WHERE isolation_state = 'isolated') AS isolated FROM aav.devices")
    q["alerts_24h"] = one("SELECT count(*) AS total, count(*) FILTER (WHERE severity = 'critical') AS critical, "
                          "count(*) FILTER (WHERE status = 'false_positive') AS false_positive FROM aav.alerts "
                          "WHERE detected_at > now() - interval '24 hours'")
    q["critical_alert_publication_seconds"] = one(
        "SELECT count(*) AS n, percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM published_at - "
        "detected_at)) AS p95, avg(CASE WHEN published_at - detected_at <= interval '30 seconds' THEN 1.0 ELSE 0.0 END) "
        "AS within_30s_ratio FROM aav.alerts WHERE severity = 'critical' AND source = 'endpoint' "
        "AND detected_at > now() - interval '30 days'")
    q["provider_alert_notification_seconds"] = one(
        "SELECT count(*) AS n, percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM notified_at - received_at)) "
        "AS p95, avg(CASE WHEN notified_at - received_at <= interval '60 seconds' THEN 1.0 ELSE 0.0 END) AS within_60s_ratio "
        "FROM aav.external_alerts WHERE severity = 'critical' AND notified_at IS NOT NULL")
    q["incidents"] = one("SELECT count(*) FILTER (WHERE status <> 'resolved') AS open, count(*) FILTER (WHERE status = "
                         "'resolved') AS resolved FROM aav.incidents")
    q["actions"] = one("SELECT count(*) AS total, count(*) FILTER (WHERE proposed_by LIKE 'ai:%%') AS ai_proposed, "
                       "count(*) FILTER (WHERE status = 'denied') AS denied, count(*) FILTER (WHERE status = 'completed') "
                       "AS completed, count(*) FILTER (WHERE status = 'failed') AS failed FROM aav.action_requests")
    q["containment_audit_coverage"] = one(
        "SELECT count(*) AS containment_actions, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM aav.audit_log l WHERE "
        "l.target = r.id::text AND l.action = 'action.propose') AND r.policy_decision <> '{}'::jsonb) AS with_decision_and_audit "
        "FROM aav.action_requests r WHERE r.action_type IN ('terminate_process','isolate_device','quarantine_file')")
    q["approval_latency_seconds"] = one(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM a.created_at - r.created_at)) AS p50, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM a.created_at - r.created_at)) AS p95 "
        "FROM aav.approvals a JOIN aav.action_requests r ON r.id = a.action_request_id")
    q["commands"] = one("SELECT count(*) FILTER (WHERE status = 'acknowledged') AS acknowledged, count(*) FILTER (WHERE "
                        "status = 'failed') AS failed, count(*) FILTER (WHERE status IN ('pending','delivered')) AS open, "
                        "count(*) FILTER (WHERE status = 'expired') AS expired FROM aav.commands")
    q["quarantine"] = one("SELECT count(*) FILTER (WHERE status = 'quarantined') AS quarantined, count(*) FILTER (WHERE "
                          "status = 'review_requested') AS review_requested, count(*) FILTER (WHERE status = 'restored') "
                          "AS restored FROM aav.quarantine_items")
    q["integrations"] = one("SELECT count(*) AS total, count(*) FILTER (WHERE maturity = 'verified_live') AS verified_live, "
                            "count(*) FILTER (WHERE maturity = 'test_only') AS test_only FROM aav.integrations")
    q["files"] = one("SELECT count(*) AS versions, COALESCE(sum(size_bytes), 0) AS bytes FROM aav.vfs_versions")
    q["audit_entries"] = one("SELECT count(*) AS n FROM aav.audit_log")
    q["freshness"] = {"computed_at": now.isoformat(), "source": "live database queries"}
    return q


@router.get("/kpis")
def kpis(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        data = _kpis(cur)
    with db.global_tx() as cur:
        cur.execute("SELECT count(*) AS failed_logins_24h FROM aav.audit_log WHERE tenant_id IS NULL AND "
                    "action = 'auth.login_failed' AND at > now() - interval '24 hours'")
        data["security_global"] = cur.fetchone()
    data["locales"] = {"catalogue": 100, "complete": sum(1 for c in i18n.coverage() if c["status"] == "complete")}
    return data


@router.get("/platform/business-kpis")
def business_kpis(u: Principal = Depends(current_user)):
    """KPI-01: active users, activation, conversion, retention and feature adoption across all tenants. Aggregates
    only; readable by the platform operators named in AAV_PLATFORM_OPERATORS."""
    from app.config import settings
    if u.email.lower() not in settings.platform_operators:
        raise HTTPException(403, "platform operators only")
    with db.global_tx() as cur:
        cur.execute("SELECT aav.business_kpis() AS k")
        return cur.fetchone()["k"]


@router.get("/kpis/export")
def kpis_export(fmt: str = "json", p: Principal = Depends(need("kpi.read"))):
    data = kpis(p)
    flat = []
    for group, vals in data.items():
        if isinstance(vals, dict):
            for k, v in vals.items():
                flat.append({"group": group, "metric": k, "value": v})
    if fmt == "json":
        return Response(json.dumps(data, default=str), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="kpis.json"'})
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["group", "metric", "value"])
        w.writeheader()
        w.writerows(flat)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="kpis.csv"'})
    if fmt == "pdf":
        from app.pdf import table_pdf
        return Response(table_pdf("KPI export " + data["freshness"]["computed_at"],
                                  [[r["group"], r["metric"], str(r["value"])] for r in flat]),
                        media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="kpis.pdf"'})
    raise HTTPException(422, "fmt must be json, csv or pdf")


@router.post("/tenants", status_code=201)
def create_child_tenant(body: TenantIn, p: Principal = Depends(need("users.manage"))):
    """USR-04: an MSP (tenant_admin of the parent) creates an independent customer tenant."""
    with db.global_tx() as cur:
        cur.execute("SELECT aav.bootstrap_tenant(%s, %s, %s) AS tid", (body.name, p.user_id, p.tenant_id))
        tid = cur.fetchone()["tid"]
    with db.tenant_tx(tid) as cur:
        cur.execute("INSERT INTO aav.memberships (tenant_id, user_id, role) VALUES (%s,%s,'msp_operator') "
                    "ON CONFLICT DO NOTHING", (tid, p.user_id))
        audit.record(cur, tenant_id=tid, actor=p.actor, action="tenant.create_child", target=str(tid),
                     detail={"parent": str(p.tenant_id)})
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="tenant.child_created", target=str(tid))
    return {"tenant_id": str(tid)}


@router.get("/tenants")
def my_tenants(p: Principal = Depends(current_user)):
    with db.global_tx() as cur:
        cur.execute("SELECT tenant_id, tenant_name, role FROM aav.user_tenants(%s)", (p.user_id,))
        return cur.fetchall()


@router.get("/members")
def members(p: Principal = Depends(need("users.manage"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT user_id, role, created_at FROM aav.memberships ORDER BY created_at")
        rows = cur.fetchall()
    # Show people by email, one row per person with all their roles (audit: UUIDs listed twice).
    with db.global_tx() as cur:
        cur.execute("SELECT id, email FROM aav.users WHERE id = ANY(%s)", ([r["user_id"] for r in rows],))
        emails = {r["id"]: r["email"] for r in cur.fetchall()}
    people: dict = {}
    for r in rows:
        e = people.setdefault(r["user_id"], {"user_id": r["user_id"], "email": emails.get(r["user_id"]),
                                             "roles": [], "created_at": r["created_at"]})
        e["roles"].append(r["role"])
    return [{**v, "role": ", ".join(v["roles"])} for v in people.values()]


@router.post("/members")
def add_role(body: MemberRoleIn, p: Principal = Depends(need("users.manage"))):
    if body.role not in rbac.ROLES:
        raise HTTPException(422, "unknown role")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT 1 FROM aav.memberships WHERE user_id = %s", (body.user_id,))
        if not cur.fetchone():
            raise HTTPException(404, "user is not a member; invite them first")
        cur.execute("INSERT INTO aav.memberships (tenant_id, user_id, role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (p.tenant_id, body.user_id, body.role))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="members.add_role", target=str(body.user_id),
                     detail={"role": body.role})
    return {"ok": True}


@router.delete("/members/{user_id}/{role}")
def remove_role(user_id: UUID, role: str, p: Principal = Depends(need("users.manage"))):
    with db.tenant_tx(p.tenant_id) as cur:
        if role == "tenant_admin":
            cur.execute("SELECT count(*) AS n FROM aav.memberships WHERE role = 'tenant_admin'")
            if cur.fetchone()["n"] <= 1:
                raise HTTPException(409, "cannot remove the last tenant administrator")
        cur.execute("DELETE FROM aav.memberships WHERE user_id = %s AND role = %s RETURNING user_id", (user_id, role))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="members.remove_role", target=str(user_id),
                     detail={"role": role})
    return {"ok": True}
