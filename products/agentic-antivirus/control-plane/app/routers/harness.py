"""Harness console API (deployment prompt §3C console views and KPIs, §3D live console and production evidence).

  /v1/harness/policy            runtime mode, kill switch, RESPOND pilot cohort (sensitive)
  /v1/harness/actions           action receipts: lifecycle, dispatch attempts, verifications, approvals
  /v1/harness/approvals         pending approval queue with age and overdue flag
  /v1/harness/actions/{id}/reconcile   settle a manual-reconciliation case with a recorded outcome
  /v1/harness/kpis              verified action success, denials, duplicate side effects, backlog, feed lag, triage time
  /v1/harness/live              deployment version, tenant, mode, per-feed last event and data age
  /v1/harness/playbooks         versioned playbook catalogue; /incidents/{id} evaluates completion criteria
  /v1/harness/assertions        production assertions (append-only evidence)
"""
from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, db, harness
from app.config import settings
from app.deps import Principal, need

router = APIRouter(prefix="/v1/harness", tags=["harness"])

STALE_FEED = timedelta(minutes=15)


def _ratio(num: int, den: int, **extra) -> dict:
    return {"numerator": num, "denominator": den, "value": "N/A" if den == 0 else round(100 * num / den, 1),
            "unit": "%", **extra}


def _pctl(values: list[float], q: float):
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 1)


# --------------------------------------------------------------------------------------------- policy
class PolicyIn(BaseModel):
    mode: str | None = None
    kill_switch: bool | None = None
    respond_cohort: list[str] | None = Field(default=None, max_length=1000)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/policy")
def get_policy(p: Principal = Depends(need("actions.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        return harness.policy(cur)


@router.put("/policy")
def put_policy(body: PolicyIn, p: Principal = Depends(need("settings.write_sensitive"))):
    changes = {}
    if body.mode is not None:
        if body.mode not in harness.MODES:
            raise HTTPException(422, f"mode must be one of {list(harness.MODES)}")
        changes["mode"] = body.mode
    if body.kill_switch is not None:
        changes["kill_switch"] = body.kill_switch
    if body.respond_cohort is not None:
        cohort = body.respond_cohort
        if cohort != ["*"]:
            try:
                cohort = [str(UUID(c)) for c in cohort]
            except ValueError:
                raise HTTPException(422, "respond_cohort holds device ids, or [\"*\"] for every device")
        changes["respond_cohort"] = cohort
    if not changes:
        raise HTTPException(422, "nothing to change")
    with db.tenant_tx(p.tenant_id) as cur:
        if "respond_cohort" in changes and changes["respond_cohort"] != ["*"]:
            cur.execute("SELECT count(*) AS n FROM aav.devices WHERE id = ANY(%s::uuid[])", (changes["respond_cohort"],))
            if cur.fetchone()["n"] != len(set(changes["respond_cohort"])):
                raise HTTPException(404, "cohort device not found in tenant")
        for key, value in changes.items():
            cur.execute("INSERT INTO aav.settings (tenant_id, category, key, value, updated_by) VALUES "
                        "(%s,'harness',%s,%s,%s) ON CONFLICT (tenant_id, category, key) DO UPDATE SET value = "
                        "EXCLUDED.value, version = aav.settings.version + 1, updated_by = EXCLUDED.updated_by, "
                        "updated_at = now() RETURNING version", (p.tenant_id, key, json.dumps(value), p.user_id))
            v = cur.fetchone()["version"]
            cur.execute("INSERT INTO aav.settings_history (tenant_id, category, key, version, value, changed_by) "
                        "VALUES (%s,'harness',%s,%s,%s,%s)", (p.tenant_id, key, v, json.dumps(value), p.user_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="harness.policy", target="harness",
                     detail={"changes": changes, "reason": body.reason})
        return harness.policy(cur)


# --------------------------------------------------------------------------------------------- receipts
@router.get("/actions")
def actions(lifecycle: str | None = None, incident_id: UUID | None = None, limit: int = 100,
            p: Principal = Depends(need("actions.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        harness.expire_stale(cur)
        harness.settle_open(cur)
        cur.execute("SELECT id, incident_id, action_type, targets, params, reason, proposed_by, status, lifecycle, "
                    "lifecycle_reason, runtime_mode, drill, policy_version, evidence_refs, idempotency_key, "
                    "targets_digest, expires_at, created_at, updated_at, verified_at FROM aav.action_requests "
                    "WHERE (%s::text IS NULL OR lifecycle = %s) AND (%s::uuid IS NULL OR incident_id = %s) "
                    "ORDER BY created_at DESC LIMIT %s",
                    (lifecycle, lifecycle, incident_id, incident_id, min(max(limit, 1), 500)))
        reqs = cur.fetchall()
        ids = [r["id"] for r in reqs]
        attempts, checks, approvals = {}, {}, {}
        if ids:
            cur.execute("SELECT action_request_id, attempt, adapter, provider_request_id, state, receipt, error, "
                        "created_at, updated_at FROM aav.action_dispatches WHERE action_request_id = ANY(%s) "
                        "ORDER BY attempt", (ids,))
            for a in cur.fetchall():
                attempts.setdefault(a.pop("action_request_id"), []).append(a)
            cur.execute("SELECT action_request_id, device_id, probe, args, expect, status, observed, source, observed_at "
                        "FROM aav.action_verifications WHERE action_request_id = ANY(%s) ORDER BY created_at", (ids,))
            for v in cur.fetchall():
                checks.setdefault(v.pop("action_request_id"), []).append(v)
            cur.execute("SELECT action_request_id, approver_id, approver_roles, expires_at, used_at, created_at "
                        "FROM aav.approvals WHERE action_request_id = ANY(%s) ORDER BY created_at", (ids,))
            for a in cur.fetchall():
                approvals.setdefault(a.pop("action_request_id"), []).append(a)
    return [{**r, "dispatches": attempts.get(r["id"], []), "verifications": checks.get(r["id"], []),
             "approvals": approvals.get(r["id"], [])} for r in reqs]


@router.get("/approvals")
def approval_queue(p: Principal = Depends(need("actions.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        harness.expire_stale(cur)
        cur.execute("SELECT id, incident_id, action_type, targets, params, reason, proposed_by, runtime_mode, drill, "
                    "evidence_refs, expires_at, created_at, "
                    "extract(epoch FROM now() - created_at)::int AS age_seconds FROM aav.action_requests "
                    "WHERE lifecycle = 'awaiting_approval' ORDER BY created_at")
        rows = cur.fetchall()
    sla = harness.APPROVAL_SLA_MINUTES * 60
    return {"sla_minutes": harness.APPROVAL_SLA_MINUTES,
            "items": [{**r, "overdue": r["age_seconds"] > sla} for r in rows]}


class ReconcileIn(BaseModel):
    outcome: str  # executed | not_executed
    evidence: str = Field(min_length=3, max_length=2000)


@router.post("/actions/{request_id}/reconcile")
def manual_reconcile(request_id: UUID, body: ReconcileIn, p: Principal = Depends(need("actions.approve"))):
    """A person records what the provider actually did after an interrupted dispatch. Not executed -> a fresh
    approval is needed before any retry; executed -> the request waits for independent verification."""
    if body.outcome not in ("executed", "not_executed"):
        raise HTTPException(422, "outcome must be executed or not_executed")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT lifecycle FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if row["lifecycle"] != "manual_reconciliation":
            raise HTTPException(409, f"not awaiting reconciliation (lifecycle {row['lifecycle']})")
        if body.outcome == "executed":
            harness.set_lifecycle(cur, request_id, "verification_pending", "reconciled by hand: executed")
        else:
            cur.execute("UPDATE aav.action_requests SET status = 'proposed' WHERE id = %s", (request_id,))
            harness.set_lifecycle(cur, request_id, "awaiting_approval", "reconciled by hand: not executed; approve again")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.reconcile_manual",
                     target=str(request_id), detail=body.model_dump())
    return {"id": str(request_id), "outcome": body.outcome}


# --------------------------------------------------------------------------------------------- KPIs
def harness_kpis(cur) -> dict:
    harness.expire_stale(cur)
    harness.settle_open(cur)
    cur.execute("SELECT lifecycle, drill, runtime_mode, count(*) AS n FROM aav.action_requests "
                "WHERE created_at >= now() - interval '30 days' AND runtime_mode IS NOT NULL "
                "GROUP BY lifecycle, drill, runtime_mode")
    rows = cur.fetchall()
    live = [r for r in rows if not r["drill"] and r["runtime_mode"] != "simulation"]
    dispatched = sum(r["n"] for r in live if r["lifecycle"] in ("verified", "failed", "verification_pending",
                                                                 "manual_reconciliation", "running"))
    verified = sum(r["n"] for r in live if r["lifecycle"] == "verified")
    cur.execute("SELECT count(*) AS n FROM aav.audit_log WHERE action = 'action.dispatch_denied' "
                "AND at >= now() - interval '30 days'")
    denials = cur.fetchone()["n"]
    cur.execute("SELECT count(*) - count(DISTINCT (action_request_id, device_id)) AS dup FROM aav.commands "
                "WHERE action_request_id IS NOT NULL")
    dup = cur.fetchone()["dup"]
    cur.execute("SELECT extract(epoch FROM now() - created_at) / 60 AS age FROM aav.action_requests "
                "WHERE lifecycle = 'awaiting_approval' AND runtime_mode IS NOT NULL")
    waiting = [float(r["age"]) for r in cur.fetchall()]
    cur.execute("SELECT extract(epoch FROM now() - created_at) / 60 AS age FROM aav.action_requests "
                "WHERE lifecycle IN ('awaiting_approval', 'queued', 'running', 'verification_pending', "
                "'manual_reconciliation') AND runtime_mode IS NOT NULL")
    backlog = [float(r["age"]) for r in cur.fetchall()]
    cur.execute("SELECT extract(epoch FROM received_at - occurred_at) AS lag FROM aav.events "
                "WHERE received_at >= now() - interval '24 hours' ORDER BY received_at DESC LIMIT 5000")
    lag = [max(0.0, float(r["lag"])) for r in cur.fetchall()]
    cur.execute("SELECT extract(epoch FROM received_at - observed_at) AS lag FROM aav.external_alerts "
                "WHERE received_at >= now() - interval '24 hours' LIMIT 5000")
    lag += [max(0.0, float(r["lag"])) for r in cur.fetchall()]
    cur.execute("SELECT extract(epoch FROM i.triaged_at - min(a.detected_at)) / 60 AS mins FROM aav.incidents i "
                "JOIN aav.alerts a ON a.incident_id = i.id WHERE i.triaged_at IS NOT NULL "
                "AND i.created_at >= now() - interval '30 days' GROUP BY i.id, i.triaged_at")
    s2t = [max(0.0, float(r["mins"])) for r in cur.fetchall()]
    cur.execute("SELECT count(*) AS n FROM aav.incidents WHERE triaged_at IS NULL AND status <> 'resolved'")
    untriaged = cur.fetchone()["n"]
    drills = sum(r["n"] for r in rows if r["drill"] or r["runtime_mode"] == "simulation")
    return {
        "window": "30 days", "cohort": "live (non-drill, non-simulation) action requests made under the harness",
        "verified_action_success": _ratio(verified, dispatched, sample=dispatched,
                                          note="Verified by independent evidence; receipts alone do not count"),
        "policy_denials": {"count": denials, "window": "30 days"},
        "duplicate_side_effects": {"count": dup, "target": 0},
        "approvals_overdue": {"count": sum(1 for a in waiting if a > harness.APPROVAL_SLA_MINUTES),
                              "waiting": len(waiting), "sla_minutes": harness.APPROVAL_SLA_MINUTES},
        "backlog_age_minutes": {"open": len(backlog), "median": _pctl(backlog, 0.5),
                                "oldest": round(max(backlog), 1) if backlog else None},
        "feed_lag_seconds": {"sample": len(lag), "median": _pctl(lag, 0.5), "p95": _pctl(lag, 0.95),
                             "value": None if not lag else _pctl(lag, 0.5)},
        "signal_to_triage_minutes": {"sample": len(s2t), "median": _pctl(s2t, 0.5), "p95": _pctl(s2t, 0.95),
                                     "open_untriaged": untriaged},
        "drill_and_simulation_requests": drills,
        "by_lifecycle": {k: sum(r["n"] for r in rows if r["lifecycle"] == k) for k in
                         ("awaiting_approval", "queued", "running", "verification_pending", "verified", "failed",
                          "denied", "expired", "manual_reconciliation")},
    }


@router.get("/kpis")
def kpis(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        return harness_kpis(cur)


# --------------------------------------------------------------------------------------------- live state
@router.get("/live")
def live(p: Principal = Depends(need("kpi.read"))):
    """§3D: version, tenant, runtime mode, most recent successful event per integration and data age.
    Live telemetry, drills and simulated feeds are labelled; missing telemetry stays Unknown."""
    with db.tenant_tx(p.tenant_id) as cur:
        pol = harness.policy(cur)
        cur.execute("SELECT name FROM aav.tenants WHERE id = %s", (p.tenant_id,))
        t = cur.fetchone()
        cur.execute("SELECT d.id::text AS id, d.hostname, d.os, d.last_seen_at, d.protection_status, "
                    "(SELECT max(e.received_at) FROM aav.events e WHERE e.device_id = d.id) AS last_event_at "
                    "FROM aav.devices d WHERE d.retired_at IS NULL ORDER BY d.hostname")
        devices = cur.fetchall()
        cur.execute("SELECT i.id::text AS id, i.name, i.signal_kind, i.maturity, i.enabled, "
                    "(SELECT max(x.received_at) FROM aav.external_alerts x WHERE x.integration_id = i.id) AS last_event_at "
                    "FROM aav.integrations i ORDER BY i.name")
        integrations = cur.fetchall()
        cur.execute("SELECT now() AS now")
        nowt = cur.fetchone()["now"]

    def feed(last, kind, maturity="verified_live"):
        if maturity in ("test_only", "stub"):
            label = "simulated"
        else:
            label = "live"
        if not last:
            return {"status": "Unknown", "data_age_seconds": None, "data": label}
        age = (nowt - last).total_seconds()
        return {"status": "Live" if age <= STALE_FEED.total_seconds() else "Stale", "data_age_seconds": int(age),
                "last_event_at": last, "data": label}

    cohort = pol["respond_cohort"]
    feeds = [{"source": f"endpoint:{d['hostname']}", "kind": "endpoint", "device_id": d["id"],
              "respond_enabled": pol["mode"] == "respond" and ("*" in cohort or d["id"] in cohort),
              "last_heartbeat_at": d["last_seen_at"], **feed(d["last_event_at"] or d["last_seen_at"], "endpoint")}
             for d in devices]
    feeds += [{"source": f"integration:{i['name']}", "kind": i["signal_kind"], "maturity": i["maturity"],
               "enabled": i["enabled"], **feed(i["last_event_at"], i["signal_kind"], i["maturity"])}
              for i in integrations]
    return {"deployment": {"build": settings.build_sha, "environment": settings.environment,
                           "policy_version": harness.POLICY_VERSION},
            "tenant": {"id": str(p.tenant_id), "name": t["name"] if t else None},
            "runtime": pol, "observed_at": nowt, "feeds": feeds,
            "coverage": {"observe": len([f for f in feeds if f["kind"] == "endpoint"]),
                         "respond": len([f for f in feeds if f.get("respond_enabled")])}}


# --------------------------------------------------------------------------------------------- playbooks
PLAYBOOKS = {
    "malware": {"version": "1.0.0", "trigger": "Engine alert, scheduled scan finding, or analyst report",
                "completion": ["detection adjudicated", "confirmed malware quarantined or removed as authorised",
                               "follow-up scan and verification recorded"]},
    "ransomware_compromise": {"version": "1.0.0", "trigger": "Corroborated endpoint and activity signals",
                              "completion": ["scope and evidence recorded", "containment verified", "source mitigated",
                                             "trusted rebuild or cleanup independently verified"]},
    "post_compromise_recovery": {"version": "1.0.0",
                                 "trigger": "Approved assessment findings or an active incident entering remediation",
                                 "completion": ["required rescans complete", "relevant mitigations verified",
                                                "protection healthy", "return-to-service approval recorded",
                                                "recurrence watch active"]},
    "network_posture": {"version": "1.0.0", "trigger": "New asset, stale sensor, missing patch or monitoring gap",
                        "completion": ["known asset reconciled", "coverage state and owner recorded",
                                       "required control verified or tracked as an open gap"]},
    "identity_phishing_egress": {"version": "1.0.0", "trigger": "Approved identity, email, DNS or flow signals",
                                 "completion": ["findings corroborated using approved sources",
                                                "scoped defensive action recorded where needed",
                                                "subsequent signals reviewed"]},
    "ddos": {"version": "1.0.0", "trigger": "Upstream alert or availability degradation",
             "completion": ["provider escalation or authorised edge action verified", "service availability checked",
                            "coverage gaps or customer impact documented"]},
    "false_positive": {"version": "1.0.0", "trigger": "Analyst adjudication disputes a detection",
                       "completion": ["evidence and decision retained", "approved restoration verified",
                                      "exception scoped with owner and expiry"]},
}


def _c(name: str, ok: bool | None, evidence: str) -> dict:
    return {"criterion": name, "status": "Unknown" if ok is None else ("PASS" if ok else "FAIL"), "evidence": evidence}


def _verified(cur, incident_id, action_types: tuple) -> int:
    cur.execute("SELECT count(*) AS n FROM aav.action_requests WHERE incident_id = %s AND lifecycle = 'verified' "
                "AND action_type = ANY(%s) AND NOT drill", (incident_id, list(action_types)))
    return cur.fetchone()["n"]


def select_playbooks(cur, inc) -> list[str]:
    cur.execute("SELECT rule_id, title, technique, status, device_id FROM aav.alerts WHERE incident_id = %s", (inc["id"],))
    alerts = cur.fetchall()
    out = []
    cat = inc["category"]
    if cat == "ddos":
        out.append("ddos")
    elif cat in ("identity", "phishing", "dns", "firewall", "email", "url_reputation", "cloud_audit"):
        out.append("identity_phishing_egress")
    else:
        text = " ".join(f"{a['title']} {a['technique'] or ''}" for a in alerts).lower()
        rules_by_device: dict = {}
        for a in alerts:
            rules_by_device.setdefault(a["device_id"], set()).add(a["rule_id"])
        corroborated = any(len(r) >= 2 for r in rules_by_device.values())
        out.append("ransomware_compromise" if "ransom" in text or "encrypt" in text or corroborated else "malware")
    if any(a["status"] == "false_positive" for a in alerts):
        out.append("false_positive")
    cur.execute("SELECT count(*) AS n FROM aav.recovery_items WHERE incident_id = %s", (inc["id"],))
    if inc["status"] == "recovering" or cur.fetchone()["n"]:
        out.append("post_compromise_recovery")
    return out


def evaluate(cur, name: str, inc) -> list[dict]:
    iid = inc["id"]
    cur.execute("SELECT id, status, device_id, detected_at FROM aav.alerts WHERE incident_id = %s", (iid,))
    alerts = cur.fetchall()
    devices = list({a["device_id"] for a in alerts if a["device_id"]})
    first = min((a["detected_at"] for a in alerts), default=None)
    cur.execute("SELECT * FROM aav.recovery_items WHERE incident_id = %s", (iid,))
    items = cur.fetchall()
    if name == "malware":
        adjudicated = sum(1 for a in alerts if a["status"] in ("triaged", "false_positive", "closed"))
        cur.execute("SELECT count(*) AS n FROM aav.quarantine_items WHERE device_id = ANY(%s) AND status IN "
                    "('quarantined', 'deleted') AND (%s::timestamptz IS NULL OR quarantined_at >= %s::timestamptz - "
                    "interval '1 hour')", (devices, first, first))
        q = cur.fetchone()["n"]
        removed = sum(1 for i in items if i["removal_state"] == "removed" and i["removal_verified_at"])
        cur.execute("SELECT count(*) AS n FROM aav.scan_jobs WHERE device_id = ANY(%s) AND status = 'complete' "
                    "AND (%s::timestamptz IS NULL OR finished_at > %s::timestamptz)", (devices, first, first))
        scans = cur.fetchone()["n"] + _verified(cur, iid, ("run_scan",))
        all_fp = alerts and all(a["status"] == "false_positive" for a in alerts)
        return [_c("detection adjudicated", bool(alerts) and adjudicated == len(alerts),
                   f"{adjudicated} of {len(alerts)} alerts adjudicated"),
                _c("confirmed malware quarantined or removed as authorised", True if all_fp else q + removed > 0,
                   "all detections were false positives" if all_fp else
                   f"{q} quarantined item(s), {removed} verified removal(s)"),
                _c("follow-up scan and verification recorded", scans > 0, f"{scans} complete scan(s) after detection")]
    if name == "ransomware_compromise":
        cur.execute("SELECT count(*) AS n FROM aav.alerts WHERE incident_id = %s AND cardinality(evidence_event_ids) > 0",
                    (iid,))
        scoped = cur.fetchone()["n"]
        contained = _verified(cur, iid, ("isolate_device", "terminate_process", "revoke_sessions", "suspend_account"))
        mitigations = [m for i in items for m in (i["mitigation"] or [])]
        cleaned = [i for i in items if (i["removal_state"] == "removed" and i["removal_verified_at"]) or
                   (i["removal_state"] == "reimage_required" and (i["restore_outcome"] or {}).get("rebuild_verified"))]
        return [_c("scope and evidence recorded", scoped > 0, f"{scoped} alert(s) with preserved evidence events"),
                _c("containment verified", contained > 0, f"{contained} independently verified containment action(s)"),
                _c("source mitigated", bool(mitigations) and all(m.get("retest_passed") is True for m in mitigations),
                   f"{sum(1 for m in mitigations if m.get('retest_passed') is True)} of {len(mitigations)} mitigation "
                   "retests passed"),
                _c("trusted rebuild or cleanup independently verified", bool(cleaned),
                   f"{len(cleaned)} asset(s) with verified removal or rebuild")]
    if name == "post_compromise_recovery":
        from app.routers.security import return_gates
        eradication = [i for i in items if i["detection_ref"] or i["removal_state"] or i["mitigation"]]
        missing = {str(i["id"]): return_gates(cur, i) for i in eradication}

        def gate_ok(word):
            if not eradication:
                return None
            return all(not any(word in m for m in ms) for ms in missing.values())
        approved = sum(1 for i in eradication if i["return_to_service_approved_by"])
        watched = sum(1 for i in eradication if i["observation_until"])
        return [_c("required rescans complete", gate_ok("recovery scan"), json.dumps(missing)[:400]),
                _c("relevant mitigations verified", gate_ok("retest"), "every mitigation needs a passing retest"),
                _c("protection healthy", gate_ok("sensor health"), "device protected and reporting"),
                _c("return-to-service approval recorded", None if not eradication else approved == len(eradication),
                   f"{approved} of {len(eradication)} approved"),
                _c("recurrence watch active", None if not eradication else watched == len(eradication),
                   f"{watched} of {len(eradication)} under observation")]
    if name == "identity_phishing_egress":
        cur.execute("SELECT count(DISTINCT integration_id) AS sources, count(*) FILTER (WHERE confirmed) AS confirmed "
                    "FROM aav.external_alerts WHERE incident_id = %s", (iid,))
        x = cur.fetchone()
        acted = _verified(cur, iid, ("revoke_sessions", "suspend_account", "isolate_device", "add_exclusion"))
        needed = inc["severity"] in ("high", "critical")
        return [_c("findings corroborated using approved sources", x["sources"] >= 2 or x["confirmed"] > 0,
                   f"{x['sources']} source(s), {x['confirmed']} confirmed signal(s)"),
                _c("scoped defensive action recorded where needed", acted > 0 or not needed,
                   f"{acted} verified action(s); action {'needed' if needed else 'not needed'} at {inc['severity']}"),
                _c("subsequent signals reviewed", inc["status"] in ("contained", "resolved"), f"incident {inc['status']}")]
    if name == "ddos":
        cur.execute("SELECT category, asset, observed_at FROM aav.external_alerts WHERE incident_id = %s "
                    "ORDER BY observed_at", (iid,))
        xs = cur.fetchall()
        started = any(x["category"] == "mitigation_started" for x in xs)
        edge = _verified(cur, iid, ("apply_traffic_policy",))
        ended = [x for x in xs if x["category"] == "mitigation_ended"]
        unhealthy_after = ended and any(x["category"] == "origin_unhealthy" and x["observed_at"] > ended[-1]["observed_at"]
                                        for x in xs)
        assets = {x["asset"] for x in xs if x["asset"]}
        cur.execute("SELECT value, provider FROM aav.protected_assets WHERE public AND value = ANY(%s)", (list(assets),))
        protected = cur.fetchall()
        cur.execute("SELECT count(*) AS n FROM aav.security_gaps WHERE status = 'open' AND subject_kind = 'endpoint'")
        gaps = cur.fetchone()["n"]
        uncovered = [a["value"] for a in protected if not a["provider"]]
        return [_c("provider escalation or authorised edge action verified", started or edge > 0,
                   f"provider mitigation evidence: {started}; verified edge actions: {edge}"),
                _c("service availability checked", None if not ended else not unhealthy_after,
                   "mitigation ended and origin healthy since" if ended and not unhealthy_after else
                   "no provider evidence that availability was restored" if not ended else "origin unhealthy after mitigation"),
                _c("coverage gaps or customer impact documented", not uncovered or gaps >= len(uncovered),
                   f"{len(uncovered)} uncovered endpoint(s), {gaps} open endpoint gap(s)")]
    if name == "false_positive":
        fp = [a for a in alerts if a["status"] == "false_positive"]
        cur.execute("SELECT count(*) AS n FROM aav.audit_log WHERE target = ANY(%s)", ([str(a["id"]) for a in fp],))
        decided = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM aav.quarantine_items WHERE device_id = ANY(%s) AND status = 'restored'",
                    (devices,))
        restored = cur.fetchone()["n"] + _verified(cur, iid, ("restore_file",))
        cur.execute("SELECT count(*) FILTER (WHERE expires_at IS NOT NULL AND approved_by IS NOT NULL) AS scoped, "
                    "count(*) AS n FROM aav.exclusions WHERE created_at >= %s::timestamptz",
                    (first or inc["created_at"],))
        ex = cur.fetchone()
        return [_c("evidence and decision retained", bool(fp) and decided > 0, f"{len(fp)} disputed alert(s), "
                   f"{decided} audit record(s)"),
                _c("approved restoration verified", None if not fp else restored > 0, f"{restored} verified restoration(s)"),
                _c("exception scoped with owner and expiry", True if ex["n"] == 0 else ex["scoped"] == ex["n"],
                   "no exception created" if ex["n"] == 0 else f"{ex['scoped']} of {ex['n']} exclusions scoped")]
    raise HTTPException(404, "unknown playbook")


@router.get("/playbooks")
def playbooks(p: Principal = Depends(need("actions.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT subject_kind, count(*) FILTER (WHERE status = 'open') AS open, "
                    "count(*) FILTER (WHERE status = 'open' AND owner <> '') AS owned FROM aav.security_gaps "
                    "GROUP BY subject_kind")
        gaps = cur.fetchall()
    open_gaps = sum(g["open"] for g in gaps)
    owned = sum(g["owned"] for g in gaps)
    posture = [_c("known asset reconciled", True, "inventory deduplicated by MAC and IP at ingest"),
               _c("coverage state and owner recorded", open_gaps == owned, f"{owned} of {open_gaps} open gaps owned"),
               _c("required control verified or tracked as an open gap", True,
                  f"{open_gaps} open gap(s) tracked; closed only on fresh verification")]
    return {"catalogue": PLAYBOOKS, "network_posture": posture}


@router.get("/incidents/{incident_id}/playbooks")
def incident_playbooks(incident_id: UUID, p: Principal = Depends(need("incidents.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.incidents WHERE id = %s", (incident_id,))
        inc = cur.fetchone()
        if not inc:
            raise HTTPException(404, "incident not found")
        harness.settle_open(cur)
        out = []
        for name in select_playbooks(cur, inc):
            criteria = evaluate(cur, name, inc)
            out.append({"playbook": name, **PLAYBOOKS[name], "criteria": criteria,
                        "complete": all(c["status"] == "PASS" for c in criteria)})
    return {"incident_id": str(incident_id), "playbooks": out}


# --------------------------------------------------------------------------------------------- assertions
class AssertionIn(BaseModel):
    requirement_id: str = Field(pattern=r"^[A-Z]{2,6}-\d{2}[A-Z]?$")
    environment: str = Field(min_length=2, max_length=40)
    scope: str = Field(min_length=1, max_length=300)
    artefact_digest: str = Field(min_length=7, max_length=200)
    outcome: str
    coverage: str = "observe"
    evidence: str = Field(min_length=3, max_length=2000)
    owner: str = Field(min_length=2, max_length=200)
    note: str = Field(default="", max_length=2000)


@router.post("/assertions", status_code=201)
def add_assertion(body: AssertionIn, p: Principal = Depends(need("settings.write_sensitive"))):
    if body.outcome not in ("PASS", "FAIL", "BLOCKED", "NOT RUN", "N/A"):
        raise HTTPException(422, "outcome must be PASS, FAIL, BLOCKED, NOT RUN or N/A")
    if body.coverage not in ("observe", "respond", "drill"):
        raise HTTPException(422, "coverage must be observe, respond or drill")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.production_assertions (tenant_id, requirement_id, environment, scope, "
                    "artefact_digest, policy_version, outcome, coverage, evidence, owner, note, recorded_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, observed_at",
                    (p.tenant_id, body.requirement_id, body.environment, body.scope, body.artefact_digest,
                     harness.POLICY_VERSION, body.outcome, body.coverage, body.evidence, body.owner, body.note, p.actor))
        row = cur.fetchone()
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="assertion.record", target=str(row["id"]),
                     detail=body.model_dump())
    return {"id": str(row["id"]), "observed_at": row["observed_at"], "policy_version": harness.POLICY_VERSION}


@router.get("/assertions")
def list_assertions(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.production_assertions ORDER BY observed_at DESC LIMIT 500")
        return cur.fetchall()
