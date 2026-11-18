"""Alerts, incidents, evidence timeline, notifications and user reports.

Trace: OPS-01 (incident queue, evidence timeline, notifications), EDR-01 (alert -> evidence),
AI-01 (correlation into incidents), USR-01 (report suspicious, warnings), USR-03, REC-01.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, db, rbac
from app.deps import Principal, need, tenant_principal

router = APIRouter(prefix="/v1", tags=["incidents"])

_SEV = ["low", "medium", "high", "critical"]


def notify(cur, tenant_id, kind: str, title: str, body: dict, user_id=None) -> None:
    cur.execute("INSERT INTO aav.notifications (tenant_id, user_id, kind, title, body) VALUES (%s,%s,%s,%s,%s)",
                (tenant_id, user_id, kind, title[:300], json.dumps(body, default=str)))


def attach_alert_to_incident(cur, tenant_id, alert_id, device_id, severity: str, title: str):
    """Correlate: join an open incident touching the same device in the last 24h, else open
    a new incident for medium+ alerts. Low alerts stay unattached until triaged."""
    cur.execute("SELECT i.id, i.severity FROM aav.incidents i JOIN aav.alerts a ON a.incident_id = i.id "
                "WHERE a.device_id = %s AND i.status <> 'resolved' AND i.updated_at > now() - interval '24 hours' "
                "ORDER BY i.updated_at DESC LIMIT 1", (device_id,))
    inc = cur.fetchone()
    if inc:
        sev = max(inc["severity"], severity, key=_SEV.index)
        cur.execute("UPDATE aav.incidents SET severity = %s, updated_at = now() WHERE id = %s", (sev, inc["id"]))
        iid = inc["id"]
    elif severity != "low":
        cur.execute("INSERT INTO aav.incidents (tenant_id, title, severity) VALUES (%s,%s,%s) RETURNING id",
                    (tenant_id, title[:300], severity))
        iid = cur.fetchone()["id"]
    else:
        return None
    cur.execute("UPDATE aav.alerts SET incident_id = %s WHERE id = %s", (iid, alert_id))
    return iid


class AlertPatch(BaseModel):
    status: str


class IncidentIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    severity: str
    alert_ids: list[UUID] = Field(default_factory=list)
    category: str = "endpoint"


class IncidentPatch(BaseModel):
    status: str | None = None
    severity: str | None = None
    assignee: UUID | None = None


class ReportIn(BaseModel):
    kind: str = Field(pattern="^(file|url|email|other)$")
    description: str = Field(min_length=3, max_length=4000)
    device_id: UUID | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    url: str | None = Field(default=None, max_length=2000)


@router.get("/alerts")
def list_alerts(status: str | None = None, severity: str | None = None, limit: int = 100, offset: int = 0,
                p: Principal = Depends(tenant_principal)):
    own_only = not rbac.allowed(p.roles, "alerts.read")
    if own_only:
        p.require("self.alerts.read")
    limit = max(1, min(limit, 500))
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT a.*, d.hostname FROM aav.alerts a LEFT JOIN aav.devices d ON d.id = a.device_id "
                    "WHERE (%s::text IS NULL OR a.status = %s) AND (%s::text IS NULL OR a.severity = %s) "
                    "AND (NOT %s OR d.owner_user_id = %s) ORDER BY a.detected_at DESC LIMIT %s OFFSET %s",
                    (status, status, severity, severity, own_only, p.user_id, limit, offset))
        return cur.fetchall()


@router.patch("/alerts/{alert_id}")
def patch_alert(alert_id: UUID, body: AlertPatch, p: Principal = Depends(need("alerts.write"))):
    if body.status not in ("new", "triaged", "false_positive", "closed"):
        raise HTTPException(422, "invalid status")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.alerts SET status = %s WHERE id = %s RETURNING id", (body.status, alert_id))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="alert.update", target=str(alert_id),
                     detail={"status": body.status})
    return {"id": str(alert_id), "status": body.status}


@router.get("/incidents")
def list_incidents(status: str | None = None, limit: int = 100, offset: int = 0,
                   p: Principal = Depends(need("incidents.read"))):
    limit = max(1, min(limit, 500))
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT i.*, (SELECT count(*) FROM aav.alerts a WHERE a.incident_id = i.id) AS alert_count "
                    "FROM aav.incidents i WHERE (%s::text IS NULL OR i.status = %s) "
                    "ORDER BY array_position(ARRAY['critical','high','medium','low'], i.severity), i.updated_at DESC "
                    "LIMIT %s OFFSET %s", (status, status, limit, offset))
        return cur.fetchall()


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentIn, p: Principal = Depends(need("incidents.write"))):
    if body.severity not in _SEV:
        raise HTTPException(422, "invalid severity")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.incidents (tenant_id, title, severity, category) VALUES (%s,%s,%s,%s) "
                    "RETURNING id", (p.tenant_id, body.title, body.severity, body.category))
        iid = cur.fetchone()["id"]
        if body.alert_ids:
            cur.execute("UPDATE aav.alerts SET incident_id = %s WHERE id = ANY(%s::uuid[])",
                        (iid, [str(a) for a in body.alert_ids]))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="incident.create", target=str(iid))
    return {"id": str(iid)}


@router.patch("/incidents/{incident_id}")
def patch_incident(incident_id: UUID, body: IncidentPatch, p: Principal = Depends(need("incidents.write"))):
    if body.status and body.status not in ("open", "investigating", "contained", "recovering", "resolved"):
        raise HTTPException(422, "invalid status")
    if body.severity and body.severity not in _SEV:
        raise HTTPException(422, "invalid severity")
    with db.tenant_tx(p.tenant_id) as cur:
        if body.status == "resolved":
            cur.execute("SELECT count(*) AS n FROM aav.recovery_items WHERE incident_id = %s AND "
                        "return_to_service_approved_by IS NULL AND step = 'return_to_service'", (incident_id,))
            if cur.fetchone()["n"]:
                raise HTTPException(409, "return to service not yet approved")
        cur.execute("UPDATE aav.incidents SET status = COALESCE(%s, status), severity = COALESCE(%s, severity), "
                    "assignee = COALESCE(%s, assignee), updated_at = now() WHERE id = %s RETURNING id",
                    (body.status, body.severity, body.assignee, incident_id))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="incident.update", target=str(incident_id),
                     detail=body.model_dump(exclude_none=True, mode="json"))
    return {"id": str(incident_id)}


def timeline_rows(cur, incident_id) -> list[dict]:
    """Evidence timeline: alerts, their linked endpoint events, external alerts, actions, and
    audit entries for the incident, each with its source id so claims can link to evidence."""
    cur.execute("SELECT id FROM aav.incidents WHERE id = %s", (incident_id,))
    if not cur.fetchone():
        raise HTTPException(404, "not found")
    items: list[dict] = []
    cur.execute("SELECT a.*, d.hostname FROM aav.alerts a LEFT JOIN aav.devices d ON d.id = a.device_id "
                "WHERE a.incident_id = %s", (incident_id,))
    alerts = cur.fetchall()
    ev_ids: list[int] = []
    for a in alerts:
        items.append({"at": a["detected_at"], "type": "alert", "ref": f"alert:{a['id']}", "device": a["hostname"],
                      "severity": a["severity"], "summary": a["title"], "rule": f"{a['rule_id']}@{a['rule_version']}",
                      "technique": a["technique"], "evidence_refs": [f"event:{e}" for e in a["evidence_event_ids"]],
                      "action_taken": a["action_taken"]})
        ev_ids.extend(a["evidence_event_ids"])
    if ev_ids:
        cur.execute("SELECT e.id, e.kind, e.occurred_at, e.data, d.hostname FROM aav.events e "
                    "JOIN aav.devices d ON d.id = e.device_id WHERE e.id = ANY(%s)", (ev_ids,))
        for e in cur.fetchall():
            items.append({"at": e["occurred_at"], "type": "event", "ref": f"event:{e['id']}", "device": e["hostname"],
                          "kind": e["kind"], "data": e["data"]})
    cur.execute("SELECT * FROM aav.external_alerts WHERE incident_id = %s", (incident_id,))
    for x in cur.fetchall():
        items.append({"at": x["observed_at"], "type": "external_alert", "ref": f"external:{x['id']}",
                      "signal": x["signal_kind"], "category": x["category"], "severity": x["severity"],
                      "asset": x["asset"], "confirmed": x["confirmed"], "data": x["data"]})
    cur.execute("SELECT id, action_type, targets, status, proposed_by, created_at, policy_decision "
                "FROM aav.action_requests WHERE incident_id = %s", (incident_id,))
    for r in cur.fetchall():
        items.append({"at": r["created_at"], "type": "action", "ref": f"action:{r['id']}",
                      "summary": f"{r['action_type']} -> {r['status']}", "targets": r["targets"],
                      "proposed_by": r["proposed_by"], "decision": r["policy_decision"]})
    items.sort(key=lambda i: i["at"])
    return items


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: UUID, p: Principal = Depends(need("incidents.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.incidents WHERE id = %s", (incident_id,))
        inc = cur.fetchone()
        if not inc:
            raise HTTPException(404, "not found")
        cur.execute("SELECT * FROM aav.investigations WHERE incident_id = %s ORDER BY created_at DESC", (incident_id,))
        inv = cur.fetchall()
        cur.execute("SELECT * FROM aav.recovery_items WHERE incident_id = %s ORDER BY updated_at", (incident_id,))
        rec = cur.fetchall()
        return {"incident": inc, "timeline": timeline_rows(cur, incident_id), "investigations": inv, "recovery": rec}


@router.get("/notifications")
def notifications(unread_only: bool = False, p: Principal = Depends(need("notifications.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.notifications WHERE (user_id IS NULL OR user_id = %s) "
                    "AND (NOT %s OR read_at IS NULL) ORDER BY created_at DESC LIMIT 200", (p.user_id, unread_only))
        return cur.fetchall()


@router.post("/notifications/{nid}/read")
def mark_read(nid: UUID, p: Principal = Depends(need("notifications.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.notifications SET read_at = now() WHERE id = %s AND (user_id IS NULL OR user_id = %s)",
                    (nid, p.user_id))
    return {"ok": True}


@router.post("/reports", status_code=201)
def report_suspicious(body: ReportIn, p: Principal = Depends(need("report.suspicious"))):
    """USR-01 / THR-02: a user reports a suspicious file, URL or message. It becomes an alert
    (source user_report) and is linked to endpoint evidence where the hash or URL matches."""
    with db.tenant_tx(p.tenant_id) as cur:
        if body.device_id:
            cur.execute("SELECT 1 FROM aav.devices WHERE id = %s", (body.device_id,))
            if not cur.fetchone():
                raise HTTPException(404, "device not found")
        linked: list[int] = []
        if body.sha256:
            cur.execute("SELECT id FROM aav.events WHERE data->>'sha256' = %s ORDER BY occurred_at DESC LIMIT 50",
                        (body.sha256,))
            linked += [r["id"] for r in cur.fetchall()]
        if body.url:
            cur.execute("SELECT id FROM aav.events WHERE data->>'url' = %s ORDER BY occurred_at DESC LIMIT 50",
                        (body.url,))
            linked += [r["id"] for r in cur.fetchall()]
        cur.execute("INSERT INTO aav.alerts (tenant_id, device_id, source, severity, title, rule_id, rule_version, "
                    "detected_at, evidence_event_ids, evidence) VALUES (%s,%s,'user_report','medium',%s,'user_report',"
                    "'1',now(),%s,%s) RETURNING id",
                    (p.tenant_id, body.device_id, f"User report: {body.kind}", linked,
                     json.dumps({"description": body.description, "sha256": body.sha256, "url": body.url,
                                 "reported_by": str(p.user_id)})))
        aid = cur.fetchone()["id"]
        iid = None
        if linked or body.kind in ("email", "url"):
            cur.execute("INSERT INTO aav.incidents (tenant_id, title, severity, category) VALUES "
                        "(%s,%s,'medium',%s) RETURNING id",
                        (p.tenant_id, f"Reported {body.kind}", "phishing" if body.kind in ("email", "url") else "endpoint"))
            iid = cur.fetchone()["id"]
            cur.execute("UPDATE aav.alerts SET incident_id = %s WHERE id = %s", (iid, aid))
            notify(cur, p.tenant_id, "report.escalated", f"Reported {body.kind} escalated",
                   {"alert_id": str(aid), "incident_id": str(iid)})
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="report.create", target=str(aid),
                     detail={"kind": body.kind, "linked_events": linked})
    return {"alert_id": str(aid), "incident_id": str(iid) if iid else None, "linked_event_ids": linked}


class RecoveryIn(BaseModel):
    step: str = Field(min_length=1, max_length=200)
    device_id: UUID | None = None


class RecoveryPatch(BaseModel):
    status: str | None = None
    restore_outcome: dict | None = None


@router.post("/incidents/{incident_id}/recovery", status_code=201)
def add_recovery(incident_id: UUID, body: RecoveryIn, p: Principal = Depends(need("recovery.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.recovery_items (tenant_id, incident_id, device_id, step) VALUES (%s,%s,%s,%s) "
                    "RETURNING id", (p.tenant_id, incident_id, body.device_id, body.step))
        rid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.add", target=str(rid))
    return {"id": str(rid)}


@router.patch("/recovery/{item_id}")
def patch_recovery(item_id: UUID, body: RecoveryPatch, p: Principal = Depends(need("recovery.write"))):
    if body.status and body.status not in ("pending", "done", "failed"):
        raise HTTPException(422, "invalid status")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.recovery_items SET status = COALESCE(%s, status), restore_outcome = COALESCE(%s, "
                    "restore_outcome), updated_at = now() WHERE id = %s RETURNING id",
                    (body.status, json.dumps(body.restore_outcome) if body.restore_outcome else None, item_id))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.update", target=str(item_id),
                     detail=body.model_dump(exclude_none=True))
    return {"id": str(item_id)}


@router.post("/recovery/{item_id}/approve-return")
def approve_return(item_id: UUID, p: Principal = Depends(need("recovery.approve_return"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.recovery_items SET return_to_service_approved_by = %s, status = 'done', "
                    "updated_at = now() WHERE id = %s AND step = 'return_to_service' RETURNING id", (p.user_id, item_id))
        if not cur.fetchone():
            raise HTTPException(404, "no return_to_service step with that id")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.return_to_service",
                     target=str(item_id), detail={"approved_at": datetime.now(timezone.utc).isoformat()})
    return {"approved": True}
