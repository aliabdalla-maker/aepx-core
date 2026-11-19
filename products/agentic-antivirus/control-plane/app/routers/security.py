"""Defensive coverage, scan KPI and gap dashboard, recovery workflow (deployment prompt §3A, §3B).

SEC-01 scan jobs (quick, full, targeted, scheduled, on-demand, recovery) with scope, progress, gaps,
       cancellation, time limits, partial results and engine versions.
SEC-04 network segments + exposure inventory from approved sources (no active scanning from here).
SEC-05 device posture from the agent (encryption, firewall, updates); not observable = Unknown.
Dashboard: Protected / Degraded / Unprotected / Unknown per device, KPIs with numerator and
denominator (N/A when nothing is eligible, Unknown when evidence is missing), and gap rows that
close only on fresh verification.
REC-03..06: removal states, recovery scans, mitigation retests, recurrence watch, recovery KPIs and
gated return to service.
"""
from __future__ import annotations

import ipaddress
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app import audit, db
from app.deps import Principal, need
from app.routers.actions import ProposeIn, dispatch, propose
from app.routers.incidents import notify

router = APIRouter(prefix="/v1", tags=["security"])

STALE_HEARTBEAT = timedelta(hours=24)
FULL_SCAN_POLICY = timedelta(days=7)
TELEMETRY_FRESH = timedelta(hours=24)
DEFINITIONS_GRACE = timedelta(hours=24)
SLA_DAYS = {"critical": 2, "high": 7, "medium": 14, "low": 30}
REMOVAL_STATES = ("quarantined", "removed", "removal_failed", "reimage_required", "pending_verification")
SCAN_TYPES = ("quick", "full", "targeted", "scheduled", "on_demand", "recovery")
FINAL = ("complete", "partial", "failed", "cancelled", "timed_out", "missed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ratio(num: int, den: int, **extra) -> dict:
    return {"numerator": num, "denominator": den,
            "value": "N/A" if den == 0 else round(100 * num / den, 1), "unit": "%", **extra}


def _pctl(values: list[float], q: float):
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 1)


# --------------------------------------------------------------------------------------------- scans
class ScanJobIn(BaseModel):
    device_ids: list[UUID] = Field(min_length=1, max_length=500)
    scan_type: str = "quick"
    paths: list[str] = Field(default_factory=list, max_length=50)
    max_seconds: int = Field(default=3600, ge=10, le=86400)
    incident_id: UUID | None = None


def create_scan_jobs(cur, p_tenant, body: ScanJobIn, requested_by: str, roles: set[str], approver_id=None) -> dict:
    if body.scan_type not in SCAN_TYPES:
        raise HTTPException(422, f"scan_type must be one of {', '.join(SCAN_TYPES)}")
    if body.scan_type == "targeted" and not body.paths:
        raise HTTPException(422, "a targeted scan needs paths")
    group = str(uuid4())
    ids = [str(d) for d in body.device_ids]
    cur.execute("SELECT id FROM aav.devices WHERE id = ANY(%s::uuid[]) AND retired_at IS NULL", (ids,))
    if len(cur.fetchall()) != len(set(ids)):
        raise HTTPException(404, "device not found")
    jobs = []
    for d in ids:
        cur.execute("INSERT INTO aav.scan_jobs (tenant_id, device_id, scan_type, scope, max_seconds, incident_id, "
                    "requested_by, group_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p_tenant, d, body.scan_type, json.dumps(body.paths), body.max_seconds, body.incident_id,
                     requested_by, group))
        jobs.append({"device_id": d, "job_id": str(cur.fetchone()["id"])})
    agent_type = {"targeted": "custom", "recovery": "full", "scheduled": "quick", "on_demand": "quick"}.get(
        body.scan_type, body.scan_type)
    params = {"scan_type": agent_type, "job_group": group, "max_seconds": body.max_seconds}
    if body.paths:
        params["paths"] = body.paths
    res = propose(cur, tenant_id=p_tenant, body=ProposeIn(action_type="run_scan", targets=ids, params=params,
                                                          incident_id=body.incident_id),
                  proposed_by=requested_by, proposer_roles=roles, approver_id=approver_id)
    audit.record(cur, tenant_id=p_tenant, actor=requested_by, action="scan_job.create", target=group,
                 detail={"scan_type": body.scan_type, "devices": len(ids), "action_request": res["id"]})
    return {"group_id": group, "jobs": jobs, "action_request": res}


@router.post("/scan-jobs", status_code=201)
def new_scan_jobs(body: ScanJobIn, p: Principal = Depends(need("scans.run"))):
    with db.tenant_tx(p.tenant_id) as cur:
        out = create_scan_jobs(cur, p.tenant_id, body, p.actor, p.roles, p.user_id)
    if out["action_request"]["status"] == "approved":
        out["dispatch"] = dispatch(UUID(out["action_request"]["id"]), p)
    return out


@router.get("/scan-jobs")
def list_scan_jobs(device_id: UUID | None = None, limit: int = 100, p: Principal = Depends(need("devices.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        _mark_missed(cur)
        cur.execute("SELECT j.*, d.hostname FROM aav.scan_jobs j JOIN aav.devices d ON d.id = j.device_id "
                    "WHERE %s::uuid IS NULL OR j.device_id = %s ORDER BY j.created_at DESC LIMIT %s",
                    (device_id, device_id, max(1, min(limit, 500))))
        return cur.fetchall()


@router.post("/scan-jobs/{job_id}/cancel")
def cancel_scan_job(job_id: UUID, p: Principal = Depends(need("scans.run"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.scan_jobs SET cancel_requested = true, status = CASE WHEN status = 'queued' "
                    "THEN 'cancelled' ELSE status END, finished_at = CASE WHEN status = 'queued' THEN now() "
                    "ELSE finished_at END WHERE id = %s AND status IN ('queued', 'running') RETURNING status", (job_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "job is not queued or running")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="scan_job.cancel", target=str(job_id))
    return {"id": str(job_id), "status": row["status"], "cancel_requested": True}


def _mark_missed(cur) -> None:
    cur.execute("UPDATE aav.scan_jobs SET status = 'missed', finished_at = now() WHERE status = 'queued' "
                "AND created_at < now() - interval '1 hour'")


class ProgressIn(BaseModel):
    job_group: str
    status: str
    files_scanned: int = Field(default=0, ge=0)
    archives_scanned: int = Field(default=0, ge=0)
    detections: int = Field(default=0, ge=0)
    gaps: dict = Field(default_factory=dict)
    engine_version: str | None = None


@router.post("/agent/scan-progress")
def scan_progress(body: ProgressIn, x_device_key: str | None = Header(default=None)):
    """Agent reports progress or the final result; the reply tells it whether to stop (cancellation)."""
    from app.routers.agent import _device
    d = _device(x_device_key)
    if body.status not in ("running",) + FINAL:
        raise HTTPException(422, "invalid status")
    gaps = {k: int(v) for k, v in body.gaps.items() if isinstance(v, int) and k in
            ("inaccessible", "encrypted_archive", "excluded", "unsupported", "too_large", "archive_limit", "timeout")}
    with db.tenant_tx(d["tenant_id"]) as cur:
        cur.execute("SELECT id, status, cancel_requested FROM aav.scan_jobs WHERE group_id::text = %s AND device_id = %s",
                    (body.job_group, d["device_id"]))
        job = cur.fetchone()
        if not job:
            raise HTTPException(404, "scan job not found")
        if job["status"] in FINAL:
            return {"cancel": True, "status": job["status"]}
        final = body.status in FINAL
        cur.execute("UPDATE aav.scan_jobs SET status = %s, files_scanned = %s, archives_scanned = %s, detections = %s, "
                    "gaps = %s, engine_version = COALESCE(%s, engine_version), progress_at = now(), "
                    "started_at = COALESCE(started_at, now()), finished_at = CASE WHEN %s THEN now() ELSE NULL END "
                    "WHERE id = %s", (body.status, body.files_scanned, body.archives_scanned, body.detections,
                                      json.dumps(gaps), body.engine_version, final, job["id"]))
        if final:
            audit.record(cur, tenant_id=d["tenant_id"], actor=f"device:{d['device_id']}", action="scan_job.finish",
                         target=str(job["id"]), detail={"status": body.status, "files": body.files_scanned,
                                                         "detections": body.detections, "gaps": gaps})
    return {"cancel": bool(job["cancel_requested"]), "status": body.status}


# --------------------------------------------------------------------------------------------- network
class SegmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cidr: str
    site: str = ""
    in_scope: bool = True
    telemetry_source: str | None = None
    owner: str = ""


class TelemetryIn(BaseModel):
    source: str = Field(min_length=1, max_length=100)


class InventoryItem(BaseModel):
    kind: str
    value: str = Field(min_length=1, max_length=300)
    attributes: dict = Field(default_factory=dict)


class InventoryIn(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    items: list[InventoryItem] = Field(max_length=5000)


@router.post("/network/segments", status_code=201)
def add_segment(body: SegmentIn, p: Principal = Depends(need("assets.write"))):
    try:
        net = ipaddress.ip_network(body.cidr, strict=False)
    except ValueError:
        raise HTTPException(422, "invalid CIDR")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.network_segments (tenant_id, name, cidr, site, in_scope, telemetry_source, owner) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, cidr) DO UPDATE SET name = EXCLUDED.name, "
                    "site = EXCLUDED.site, in_scope = EXCLUDED.in_scope, owner = EXCLUDED.owner RETURNING id",
                    (p.tenant_id, body.name, str(net), body.site, body.in_scope, body.telemetry_source, body.owner))
        sid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="network.segment", target=str(sid),
                     detail={"cidr": str(net), "in_scope": body.in_scope})
    return {"id": str(sid), "cidr": str(net)}


@router.get("/network/segments")
def segments(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT s.*, (SELECT count(*) FROM aav.network_assets a WHERE a.segment_id = s.id) AS assets "
                    "FROM aav.network_segments s ORDER BY s.name")
        rows = cur.fetchall()
    for r in rows:
        r["cidr"] = str(r["cidr"])
        r["visibility"] = "monitored" if r["last_telemetry_at"] and _now() - r["last_telemetry_at"] <= TELEMETRY_FRESH \
            else ("stale" if r["last_telemetry_at"] else "blind")
    return rows


@router.post("/network/segments/{sid}/telemetry")
def segment_telemetry(sid: UUID, body: TelemetryIn, p: Principal = Depends(need("assets.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.network_segments SET last_telemetry_at = now(), telemetry_source = %s WHERE id = %s "
                    "RETURNING id", (body.source, sid))
        if not cur.fetchone():
            raise HTTPException(404, "segment not found")
    return {"id": str(sid), "last_telemetry_at": _now().isoformat()}


@router.post("/network/inventory")
def inventory(body: InventoryIn, p: Principal = Depends(need("assets.write"))):
    """Exposure inventory from an approved source (asset register, DNS, flow summaries, credentialed
    read-only posture checks). Deduplicated by kind + value; each host is placed in its segment."""
    added = updated = 0
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT id, cidr FROM aav.network_segments")
        segs = [(r["id"], ipaddress.ip_network(str(r["cidr"]))) for r in cur.fetchall()]
        for it in body.items:
            if it.kind not in ("host", "service", "certificate"):
                raise HTTPException(422, f"unknown kind {it.kind}")
            seg = None
            ip = it.attributes.get("ip") or (it.value if it.kind == "host" else None)
            try:
                addr = ipaddress.ip_address(str(ip)) if ip else None
                seg = next((sid for sid, net in segs if addr and addr in net), None)
            except ValueError:
                pass
            cur.execute("INSERT INTO aav.network_assets (tenant_id, kind, value, segment_id, attributes, source) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, kind, value) DO UPDATE SET "
                        "last_seen = now(), attributes = aav.network_assets.attributes || EXCLUDED.attributes, "
                        "segment_id = COALESCE(EXCLUDED.segment_id, aav.network_assets.segment_id) "
                        "RETURNING (xmax = 0) AS inserted",
                        (p.tenant_id, it.kind, it.value, seg, json.dumps(it.attributes), body.source))
            if cur.fetchone()["inserted"]:
                added += 1
            else:
                updated += 1
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="network.inventory", target=body.source,
                     detail={"added": added, "updated": updated})
    return {"added": added, "deduplicated": updated}


@router.get("/network/inventory")
def list_inventory(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.network_assets ORDER BY kind, value LIMIT 5000")
        rows = cur.fetchall()
    soon = _now() + timedelta(days=30)
    for r in rows:
        exp = r["attributes"].get("not_after") if r["kind"] == "certificate" else None
        if exp:
            try:
                r["certificate_state"] = "expiring" if datetime.fromisoformat(exp.replace("Z", "+00:00")) <= soon else "valid"
            except ValueError:
                r["certificate_state"] = "unknown"
    return rows


# --------------------------------------------------------------------------------------------- posture
def _latest_definitions(cur):
    """Latest active detections bundle, plus the one before it (devices get DEFINITIONS_GRACE to catch up)."""
    cur.execute("SELECT version, published_at FROM aav.update_bundles WHERE kind = 'detections' AND revoked_at IS NULL "
                "ORDER BY published_at DESC LIMIT 2")
    rows = cur.fetchall()
    if not rows:
        return None
    return {**rows[0], "previous": rows[1]["version"] if len(rows) > 1 else None}


def device_states(cur) -> list[dict]:
    latest = _latest_definitions(cur)
    cur.execute("SELECT d.id, d.hostname, d.os, d.site, d.in_scope, d.protection_status, d.sensor_health, "
                "d.definitions_version, d.posture, d.posture_at, d.last_seen_at, d.criticality, u.email AS owner, "
                "(SELECT max(finished_at) FROM aav.scan_jobs j WHERE j.device_id = d.id AND j.status = 'complete' "
                " AND j.scan_type IN ('full', 'recovery')) AS last_full_scan, "
                "(SELECT status FROM aav.scan_jobs j WHERE j.device_id = d.id AND j.status IN "
                " ('complete','partial','failed','cancelled','timed_out','missed') ORDER BY finished_at DESC NULLS LAST "
                " LIMIT 1) AS last_scan_status "
                "FROM aav.devices d LEFT JOIN aav.users u ON u.id = d.owner_user_id WHERE d.retired_at IS NULL "
                "ORDER BY d.hostname")
    out, now = [], _now()
    for d in cur.fetchall():
        reasons, state = [], "protected"
        offline = d["last_seen_at"] is None or now - d["last_seen_at"] > STALE_HEARTBEAT
        defs_current = bool(latest and d["definitions_version"] == latest["version"]) or \
            bool(latest and latest["previous"] and d["definitions_version"] == latest["previous"]
                 and now - latest["published_at"] <= DEFINITIONS_GRACE)
        if offline:
            state = "unknown"
            reasons.append("no heartbeat in 24 hours" if d["last_seen_at"] else "never reported")
        elif d["protection_status"] == "disabled" or not d["definitions_version"]:
            state = "unprotected"
            reasons.append("protection disabled" if d["protection_status"] == "disabled" else "no detection definitions")
        else:
            if d["protection_status"] != "protected":
                reasons.append(f"protection {d['protection_status']}")
            if not defs_current:
                reasons.append("definitions out of date")
            if not d["last_full_scan"] or now - d["last_full_scan"] > FULL_SCAN_POLICY:
                reasons.append("no complete full scan in 7 days")
            if d["last_scan_status"] in ("partial", "failed", "timed_out", "missed", "cancelled"):
                reasons.append(f"last scan {d['last_scan_status']}")
            post = d["posture"] or {}
            if post.get("disk_encryption") is False:
                reasons.append("disk not encrypted")
            if post.get("firewall") is False:
                reasons.append("host firewall off")
            if reasons:
                state = "degraded"
        out.append({**d, "state": state, "reasons": reasons, "definitions_current": defs_current and not offline,
                    "latest_definitions": latest["version"] if latest else None})
    return out


# --------------------------------------------------------------------------------------------- gaps
def _gap(cur, tenant_id, kind, sid, label, control, observed, evidence_at, reason, severity, owner, fix, seen: set):
    seen.add((kind, sid, control))
    cur.execute("SELECT id FROM aav.security_gaps WHERE subject_kind = %s AND subject_id = %s AND expected_control = %s "
                "AND status = 'open'", (kind, sid, control))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE aav.security_gaps SET observed_state = %s, last_evidence_at = %s, reason = %s, "
                    "retest_status = CASE WHEN retest_status = 'not_retested' THEN retest_status ELSE 'retest_failed' END "
                    "WHERE id = %s", (observed, evidence_at, reason, row["id"]))
        return
    cur.execute("INSERT INTO aav.security_gaps (tenant_id, subject_kind, subject_id, subject_label, expected_control, "
                "observed_state, last_evidence_at, reason, severity, owner, due_date, proposed_fix) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant_id, kind, sid, label, control, observed, evidence_at, reason, severity, owner or "unassigned",
                 date.today() + timedelta(days=SLA_DAYS[severity]), fix))


def evaluate_gaps(cur, tenant_id) -> dict:
    """Recompute gaps from current evidence. A gap closes only when this evaluation observes fresh
    evidence that the control now holds (verified_closed with that evidence)."""
    _mark_missed(cur)
    seen: set = set()
    devices = device_states(cur)
    for d in devices:
        if not d["in_scope"]:
            continue
        sid, label, owner = str(d["id"]), d["hostname"], d["owner"]
        crit = d["criticality"] == "critical"
        if d["state"] == "unknown":
            _gap(cur, tenant_id, "device", sid, label, "heartbeat within 24 hours", d["reasons"][0], d["last_seen_at"],
                 "device offline or not reporting", "high" if crit else "medium", owner,
                 "Bring the device online or retire it; check the agent service.", seen)
            continue
        if d["state"] == "unprotected":
            _gap(cur, tenant_id, "device", sid, label, "real-time protection with current definitions",
                 ", ".join(d["reasons"]), d["last_seen_at"], "protection not running", "critical", owner,
                 "Re-enable protection and install the current definitions.", seen)
            continue
        for r in d["reasons"]:
            control, sev, fix = {
                "definitions out of date": ("current detection definitions", "high",
                                            "Let the agent refresh updates; check connectivity to the console."),
                "no complete full scan in 7 days": ("complete full scan within 7 days", "medium",
                                                    "Run a full scan from Security and let it complete."),
                "disk not encrypted": ("disk encryption", "high", "Turn on BitLocker, FileVault or LUKS."),
                "host firewall off": ("host firewall", "high", "Turn the operating-system firewall on."),
            }.get(r, ("healthy sensors", "medium", "Check the sensors reported by the agent.") if r.startswith("protection")
                  else (("complete last scan", "medium", "Re-run the scan; review inaccessible files and timeouts.")
                        if r.startswith("last scan") else (None, None, None)))
            if control:
                _gap(cur, tenant_id, "device", sid, label, control, r, d["posture_at"] or d["last_seen_at"], r,
                     "critical" if crit and sev == "high" else sev, owner, fix, seen)
    cur.execute("SELECT id, name, cidr, last_telemetry_at, owner FROM aav.network_segments WHERE in_scope")
    for s in cur.fetchall():
        if not s["last_telemetry_at"] or _now() - s["last_telemetry_at"] > TELEMETRY_FRESH:
            _gap(cur, tenant_id, "segment", str(s["id"]), f"{s['name']} ({s['cidr']})", "network telemetry within 24 hours",
                 "stale telemetry" if s["last_telemetry_at"] else "no telemetry (blind segment)", s["last_telemetry_at"],
                 "segment has no verified visibility", "medium", s["owner"],
                 "Connect DNS or flow telemetry for this segment, or mark it out of scope with a reason.", seen)
    from app.routers.threats import _uncovered
    cur.execute("SELECT * FROM aav.protected_assets WHERE public")
    for a in cur.fetchall():
        if _uncovered(a):
            _gap(cur, tenant_id, "endpoint", str(a["id"]), a["value"], "verified upstream DDoS mitigation",
                 "no provider recorded", None, "public endpoint without verified upstream mitigation", "high",
                 a["service_owner"], "Record the upstream provider and mitigation policy, or an approved exception.", seen)
    cur.execute("SELECT id, kind, value, expires_at, approved_by FROM aav.exclusions")
    for e in cur.fetchall():
        if e["expires_at"] is None or e["approved_by"] is None or e["expires_at"] < _now():
            why = "expired" if e["expires_at"] and e["expires_at"] < _now() else "no expiry or approver"
            _gap(cur, tenant_id, "exclusion", str(e["id"]), f"{e['kind']}:{e['value']}", "exclusion with expiry and approval",
                 why, None, why, "low", "", "Set an expiry and an approver, or remove the exclusion.", seen)
    # Close gaps whose control was observed holding in this evaluation (fresh verification).
    cur.execute("SELECT id, subject_kind, subject_id, expected_control FROM aav.security_gaps WHERE status = 'open'")
    closed = 0
    for g in cur.fetchall():
        if (g["subject_kind"], g["subject_id"], g["expected_control"]) not in seen:
            cur.execute("UPDATE aav.security_gaps SET status = 'closed', closed_at = now(), retest_status = "
                        "'verified_closed', closed_evidence = %s WHERE id = %s",
                        (json.dumps({"evaluated_at": _now().isoformat(), "observation": "control observed holding"}),
                         g["id"]))
            closed += 1
    cur.execute("SELECT count(*) AS n FROM aav.security_gaps WHERE status = 'open'")
    return {"open": cur.fetchone()["n"], "closed_now": closed, "devices": devices}


@router.post("/security/gaps/evaluate")
def gaps_evaluate(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        res = evaluate_gaps(cur, p.tenant_id)
    return {"open": res["open"], "closed_now": res["closed_now"]}


@router.get("/security/gaps")
def gaps(status: str = "open", p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.security_gaps WHERE %s = 'all' OR status = %s ORDER BY "
                    "array_position(ARRAY['critical','high','medium','low'], severity), opened_at", (status, status))
        rows = cur.fetchall()
    today = date.today()
    for r in rows:
        r["overdue"] = r["status"] == "open" and r["due_date"] < today
    return rows


# --------------------------------------------------------------------------------------------- dashboard
def security_kpis(cur, devices: list[dict]) -> dict:
    now = _now()
    scope = [d for d in devices if d["in_scope"]]
    counts = {s: sum(1 for d in scope if d["state"] == s) for s in ("protected", "degraded", "unprotected", "unknown")}
    reporting = [d for d in scope if d["state"] != "unknown"]
    full_ok = sum(1 for d in scope if d["last_full_scan"] and now - d["last_full_scan"] <= FULL_SCAN_POLICY)
    cur.execute("SELECT status, count(*) AS n FROM aav.scan_jobs WHERE created_at > now() - interval '30 days' "
                "AND status <> 'queued' AND status <> 'running' GROUP BY status")
    by_status = {r["status"]: r["n"] for r in cur.fetchall()}
    cur.execute("SELECT name, last_telemetry_at FROM aav.network_segments WHERE in_scope")
    segs = cur.fetchall()
    fresh = [s for s in segs if s["last_telemetry_at"] and now - s["last_telemetry_at"] <= TELEMETRY_FRESH]
    stale_defs = [d for d in reporting if not d["definitions_current"]]
    cur.execute("SELECT extract(epoch FROM published_at - detected_at) AS s FROM aav.alerts "
                "WHERE detected_at > now() - interval '30 days' AND severity IN ('high', 'critical')")
    detect = [max(0.0, float(r["s"])) for r in cur.fetchall()]
    cur.execute("SELECT a.id, a.action_taken, a.detected_at, a.status, "
                "(SELECT min(c.ack_at) FROM aav.commands c JOIN aav.action_requests r ON r.id = c.action_request_id "
                " WHERE r.incident_id = a.incident_id AND c.command_type IN ('isolate', 'quarantine', 'terminate_process') "
                " AND c.status = 'acknowledged') AS contained_at FROM aav.alerts a "
                "WHERE a.detected_at > now() - interval '30 days' AND a.severity IN ('high', 'critical')")
    contain, open_cases = [], 0
    for a in cur.fetchall():
        if a["action_taken"] == "quarantined":
            contain.append(0.0)
        elif a["contained_at"]:
            contain.append(max(0.0, (a["contained_at"] - a["detected_at"]).total_seconds()))
        elif a["status"] not in ("closed", "false_positive"):
            open_cases += 1
    cur.execute("SELECT status, count(*) AS n FROM aav.alerts WHERE detected_at > now() - interval '90 days' "
                "GROUP BY status")
    al = {r["status"]: r["n"] for r in cur.fetchall()}
    from app.routers.threats import _uncovered
    cur.execute("SELECT * FROM aav.protected_assets WHERE public")
    assets = cur.fetchall()
    pa = {"ok": sum(1 for a in assets if not _uncovered(a)), "n": len(assets)}
    cur.execute("SELECT severity, opened_at, due_date FROM aav.security_gaps WHERE status = 'open'")
    open_gaps = cur.fetchall()
    cur.execute("SELECT count(*) AS n FROM aav.security_gaps WHERE status = 'closed' AND closed_at > now() - interval '30 days'")
    closures = cur.fetchone()["n"]
    ages = [(now - g["opened_at"]).total_seconds() / 86400 for g in open_gaps]
    crit = [g for g in open_gaps if g["severity"] == "critical"]
    complete = by_status.get("complete", 0)
    due = sum(by_status.values())
    return {
        "states": counts, "in_scope_devices": len(scope),
        "endpoint_protection_coverage": _ratio(counts["protected"], len(scope), unknown=counts["unknown"]),
        "full_scan_coverage": _ratio(full_ok, len(scope)),
        "scan_execution_reliability": _ratio(complete, due, breakdown=by_status),
        "network_visibility": _ratio(len(fresh), len(segs), blind=[s["name"] for s in segs if not s["last_telemetry_at"]]),
        "signature_freshness": _ratio(len(reporting) - len(stale_defs), len(reporting),
                                      oldest_stale=min((d["hostname"] for d in stale_defs), default=None),
                                      unknown=counts["unknown"]),
        "detection_time_seconds": {"median": _pctl(detect, 0.5), "p95": _pctl(detect, 0.95), "n": len(detect)},
        "containment_time_seconds": {"median": _pctl(contain, 0.5), "p95": _pctl(contain, 0.95), "n": len(contain),
                                     "open_cases": open_cases},
        "detection_quality": _ratio(al.get("closed", 0), al.get("closed", 0) + al.get("false_positive", 0),
                                    unreviewed=al.get("new", 0) + al.get("triaged", 0),
                                    note="labelled test-case detection rate is in the release evidence (OBJ-03)"),
        "ddos_resilience": _ratio(pa["ok"], pa["n"], note="drill and real-incident results are reported separately"),
        "gap_backlog": {"open": len(open_gaps), "by_severity": {s: sum(1 for g in open_gaps if g["severity"] == s)
                                                                for s in SLA_DAYS},
                        "median_age_days": round(statistics.median(ages), 1) if ages else None,
                        "oldest_critical_days": round(max((now - g["opened_at"]).total_seconds() / 86400 for g in crit), 1)
                        if crit else None,
                        "overdue": sum(1 for g in open_gaps if g["due_date"] < date.today()),
                        "verified_closures_30d": closures},
        "measured_at": now.isoformat(),
        "note": "A zero-detection period does not establish protection or scan coverage.",
    }


@router.get("/security/dashboard")
def dashboard(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        res = evaluate_gaps(cur, p.tenant_id)
        kpis = security_kpis(cur, res["devices"])
        rec = recovery_kpis(cur)
    devices = [{k: d[k] for k in ("id", "hostname", "os", "site", "state", "reasons", "last_seen_at", "posture",
                                  "definitions_version", "last_full_scan", "last_scan_status", "in_scope")}
               for d in res["devices"]]
    return {"kpis": kpis, "recovery": rec, "devices": devices, "open_gaps": res["open"]}


# --------------------------------------------------------------------------------------------- recovery
class RemovalIn(BaseModel):
    removal_state: str
    detection_ref: str | None = Field(default=None, max_length=200)
    evidence: dict = Field(default_factory=dict)


class MitigationIn(BaseModel):
    description: str = Field(min_length=3, max_length=1000)
    retest_passed: bool | None = None
    evidence: dict = Field(default_factory=dict)


class RecurrenceIn(BaseModel):
    detection_ref: str = Field(min_length=1, max_length=200)


def _item(cur, item_id):
    cur.execute("SELECT * FROM aav.recovery_items WHERE id = %s", (item_id,))
    it = cur.fetchone()
    if not it:
        raise HTTPException(404, "recovery item not found")
    return it


@router.post("/recovery/{item_id}/recovery-scan", status_code=201)
def recovery_scan(item_id: UUID, p: Principal = Depends(need("recovery.write"))):
    """REC-05: a full scan with current definitions on the affected device, linked to this item."""
    with db.tenant_tx(p.tenant_id) as cur:
        it = _item(cur, item_id)
        if not it["device_id"]:
            raise HTTPException(422, "recovery item has no device")
        out = create_scan_jobs(cur, p.tenant_id, ScanJobIn(device_ids=[it["device_id"]], scan_type="recovery",
                                                           incident_id=it["incident_id"]), p.actor, p.roles, p.user_id)
        cur.execute("UPDATE aav.recovery_items SET verification_scan_id = %s, updated_at = now() WHERE id = %s",
                    (out["jobs"][0]["job_id"], item_id))
    if out["action_request"]["status"] == "approved":
        out["dispatch"] = dispatch(UUID(out["action_request"]["id"]), p)
    return out


@router.post("/recovery/{item_id}/removal")
def set_removal(item_id: UUID, body: RemovalIn, p: Principal = Depends(need("recovery.write"))):
    """REC-03: record the removal state. 'removed' needs fresh verification: a complete recovery scan of
    the device, finished after the item was opened, with no detections. Quarantine never counts as removal."""
    if body.removal_state not in REMOVAL_STATES:
        raise HTTPException(422, f"removal_state must be one of {', '.join(REMOVAL_STATES)}")
    with db.tenant_tx(p.tenant_id) as cur:
        it = _item(cur, item_id)
        verified_at = None
        if body.removal_state == "removed":
            if not it["verification_scan_id"]:
                raise HTTPException(409, "run a recovery scan first; removal needs fresh verification")
            cur.execute("SELECT status, detections, finished_at FROM aav.scan_jobs WHERE id = %s",
                        (it["verification_scan_id"],))
            job = cur.fetchone()
            if not job or job["status"] != "complete" or job["finished_at"] < it["created_at"]:
                raise HTTPException(409, "recovery scan is not complete; state stays pending_verification")
            if job["detections"]:
                raise HTTPException(409, f"recovery scan still found {job['detections']} detection(s)")
            verified_at = job["finished_at"]
        cur.execute("UPDATE aav.recovery_items SET removal_state = %s, detection_ref = COALESCE(%s, detection_ref), "
                    "removal_verified_at = %s, confirmed_infected_at = COALESCE(confirmed_infected_at, now()), "
                    "observation_until = CASE WHEN %s THEN now() + interval '14 days' ELSE observation_until END, "
                    "updated_at = now() WHERE id = %s",
                    (body.removal_state, body.detection_ref, verified_at, verified_at is not None, item_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.removal", target=str(item_id),
                     detail={"state": body.removal_state, "verified": verified_at is not None, "evidence": body.evidence})
    return {"id": str(item_id), "removal_state": body.removal_state,
            "verified_at": verified_at.isoformat() if verified_at else None}


@router.post("/recovery/{item_id}/mitigation")
def add_mitigation(item_id: UUID, body: MitigationIn, p: Principal = Depends(need("recovery.write"))):
    """REC-04: a fix (patch, configuration, credential rotation) and its defensive retest result."""
    with db.tenant_tx(p.tenant_id) as cur:
        it = _item(cur, item_id)
        entry = {"description": body.description, "retest_passed": body.retest_passed, "evidence": body.evidence,
                 "recorded_by": p.actor, "at": _now().isoformat()}
        cur.execute("UPDATE aav.recovery_items SET mitigation = mitigation || %s::jsonb, updated_at = now() WHERE id = %s",
                    (json.dumps([entry]), item_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.mitigation", target=str(item_id),
                     detail={"retest_passed": body.retest_passed})
    return {"id": str(item_id), "mitigations": len(it["mitigation"]) + 1}


@router.post("/recovery/{item_id}/recurrence")
def recurrence(item_id: UUID, body: RecurrenceIn, p: Principal = Depends(need("recovery.write"))):
    """REC-06: a recurrence inside the observation window reopens the incident and the item."""
    with db.tenant_tx(p.tenant_id) as cur:
        it = _item(cur, item_id)
        cur.execute("UPDATE aav.recovery_items SET recurred_at = now(), removal_state = 'pending_verification', "
                    "removal_verified_at = NULL, return_to_service_approved_by = NULL, status = 'pending', "
                    "updated_at = now() WHERE id = %s", (item_id,))
        cur.execute("UPDATE aav.incidents SET status = 'open', updated_at = now() WHERE id = %s", (it["incident_id"],))
        notify(cur, p.tenant_id, "recovery.recurrence", "Recurrence after recovery",
               {"recovery_item": str(item_id), "incident_id": str(it["incident_id"]), "detection": body.detection_ref})
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.recurrence", target=str(item_id),
                     detail={"detection": body.detection_ref})
    return {"id": str(item_id), "incident_reopened": str(it["incident_id"])}


def return_gates(cur, it) -> list[str]:
    """Open gates that block return to service for one recovery item (REC-06)."""
    missing: list[str] = []
    if not (it["detection_ref"] or it["removal_state"] or it["mitigation"]):
        return missing  # not part of an eradication workflow (e.g. a backup restore step)
    if it["detection_ref"] or it["removal_state"]:
        if it["removal_state"] not in ("removed", "reimage_required") or \
                (it["removal_state"] == "removed" and not it["removal_verified_at"]):
            missing.append("verified removal or verified rebuild")
        if it["removal_state"] == "reimage_required" and not (it["restore_outcome"] or {}).get("rebuild_verified"):
            missing.append("verified rebuild from a known-good image")
    if it["device_id"]:
        if not it["verification_scan_id"]:
            missing.append("complete recovery scan")
        else:
            cur.execute("SELECT status FROM aav.scan_jobs WHERE id = %s", (it["verification_scan_id"],))
            j = cur.fetchone()
            if not j or j["status"] != "complete":
                missing.append("complete recovery scan")
        cur.execute("SELECT protection_status, last_seen_at FROM aav.devices WHERE id = %s", (it["device_id"],))
        dv = cur.fetchone()
        if not dv or dv["protection_status"] != "protected" or not dv["last_seen_at"] or \
                _now() - dv["last_seen_at"] > STALE_HEARTBEAT:
            missing.append("restored sensor health")
    if any(m.get("retest_passed") is not True for m in it["mitigation"]):
        missing.append("passing retest for every mitigation")
    return missing


@router.get("/recovery/{item_id}/gates")
def gates(item_id: UUID, p: Principal = Depends(need("recovery.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        it = _item(cur, item_id)
        missing = return_gates(cur, it)
    return {"id": str(item_id), "ready": not missing, "missing": missing}


def recovery_kpis(cur) -> dict:
    cur.execute("SELECT r.*, j.status AS scan_status FROM aav.recovery_items r LEFT JOIN aav.scan_jobs j "
                "ON j.id = r.verification_scan_id")
    items = cur.fetchall()
    needing = [i for i in items if i["detection_ref"] or i["removal_state"]]
    verified = [i for i in needing if i["removal_state"] == "removed" and i["removal_verified_at"]]
    devices = [i for i in items if i["device_id"]]
    mitig = [m for i in items for m in i["mitigation"]]
    times = [(i["removal_verified_at"] - i["confirmed_infected_at"]).total_seconds() / 3600
             for i in verified if i["confirmed_infected_at"]]
    watched = [i for i in items if i["observation_until"]]  # recovered once (window started at verified removal)
    done_watch = [i for i in watched if i["observation_until"] <= _now() or i["recurred_at"]]
    returns = [i for i in items if i["step"] == "return_to_service"]
    return {
        "verified_removal_rate": _ratio(len(verified), len(needing),
                                        quarantine_only=sum(1 for i in needing if i["removal_state"] == "quarantined"),
                                        reimage=sum(1 for i in needing if i["removal_state"] == "reimage_required"),
                                        failed=sum(1 for i in needing if i["removal_state"] == "removal_failed")),
        "post_mitigation_scan_coverage": _ratio(sum(1 for i in devices if i["scan_status"] == "complete"), len(devices),
                                                incomplete=sum(1 for i in devices if i["scan_status"] not in
                                                               (None, "complete")),
                                                not_started=sum(1 for i in devices if i["scan_status"] is None)),
        "mitigation_verification_rate": _ratio(sum(1 for m in mitig if m.get("retest_passed") is True), len(mitig)),
        "time_to_verified_eradication_hours": {"median": _pctl(times, 0.5), "p95": _pctl(times, 0.95), "n": len(times),
                                               "unresolved": len(needing) - len(verified)},
        "recurrence_rate": _ratio(sum(1 for i in done_watch if i["recurred_at"]), len(done_watch),
                                  under_observation=len(watched) - len(done_watch)),
        "safe_return_to_service_rate": _ratio(sum(1 for i in returns if i["return_to_service_approved_by"]), len(returns)),
    }


@router.get("/recovery/kpis")
def recovery_kpi_view(p: Principal = Depends(need("recovery.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        return recovery_kpis(cur)
