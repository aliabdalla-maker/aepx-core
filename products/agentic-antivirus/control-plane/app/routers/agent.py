"""Device-facing API used by the endpoint agent.

Trace: ARC-01, ARC-02, OPS-02 (signed policy/updates, replay), EDR-01 (events -> alerts linked to
evidence), EDR-02 (command acks, isolation state), AV-02 (quarantine reports), OBJ-04 (alert
publication latency is measured from detected_at to published_at), NFR-02 (bounded batches,
duplicate-safe replay).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db
from app.routers.incidents import attach_alert_to_incident, notify

router = APIRouter(prefix="/v1/agent", tags=["agent"])

MAX_BATCH = 1000


class EnrolIn(BaseModel):
    token: str
    hostname: str = Field(min_length=1, max_length=255)
    os: str
    os_version: str = Field(default="", max_length=100)
    agent_version: str = Field(default="", max_length=50)


class HeartbeatIn(BaseModel):
    agent_version: str = ""
    definitions_version: str | None = None
    applied_policy_version: int | None = None
    protection_status: str = "unknown"
    sensor_health: dict = Field(default_factory=dict)


class EventIn(BaseModel):
    event_uid: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=50)
    occurred_at: datetime
    data: dict


class EventBatch(BaseModel):
    events: list[EventIn]


class AckIn(BaseModel):
    status: str
    result: dict = Field(default_factory=dict)


def _device(x_device_key: str | None) -> dict:
    if not x_device_key:
        raise HTTPException(401, "device key required")
    with db.global_tx() as cur:
        cur.execute("SELECT device_id, tenant_id FROM aav.device_by_key(%s)", (crypto.token_hash(x_device_key),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(401, "unknown or retired device")
    return row


@router.post("/enrol", status_code=201)
def enrol(body: EnrolIn):
    if body.os not in ("windows", "macos", "linux", "android", "ios"):
        raise HTTPException(422, "unsupported os")
    with db.global_tx() as cur:
        cur.execute("SELECT aav.consume_enrollment_token(%s) AS tid", (crypto.token_hash(body.token),))
        tid = cur.fetchone()["tid"]
    if not tid:
        raise HTTPException(401, "invalid, expired or exhausted enrolment token")
    device_key = crypto.new_token(48)
    with db.tenant_tx(tid) as cur:
        cur.execute("INSERT INTO aav.devices (tenant_id, hostname, os, os_version, agent_version, device_key_hash, "
                    "policy_name) VALUES (%s,%s,%s,%s,%s,%s,'default') RETURNING id",
                    (tid, body.hostname, body.os, body.os_version, body.agent_version, crypto.token_hash(device_key)))
        did = cur.fetchone()["id"]
        audit.record(cur, tenant_id=tid, actor=f"device:{did}", action="device.enrol", target=str(did),
                     detail={"hostname": body.hostname, "os": body.os})
    return {"device_id": str(did), "tenant_id": str(tid), "device_key": device_key,
            "control_plane_public_key": crypto.public_key_pem(), "key_id": crypto.key_id()}


@router.get("/policy")
def policy(x_device_key: str | None = Header(default=None)):
    d = _device(x_device_key)
    with db.tenant_tx(d["tenant_id"]) as cur:
        cur.execute("SELECT policy_name FROM aav.devices WHERE id = %s", (d["device_id"],))
        name = cur.fetchone()["policy_name"] or "default"
        cur.execute("SELECT version, body FROM aav.policies WHERE name = %s ORDER BY version DESC LIMIT 1", (name,))
        pol = cur.fetchone()
        if not pol:
            raise HTTPException(404, f"no policy '{name}' published for this tenant")
        cur.execute("SELECT kind, value FROM aav.exclusions ORDER BY created_at")
        exclusions = cur.fetchall()
        cur.execute("SELECT scan_type, cron FROM aav.scan_schedules WHERE policy_name = %s", (name,))
        schedules = cur.fetchall()
    bundle = {"tenant_id": str(d["tenant_id"]), "device_id": str(d["device_id"]), "name": name,
              "version": pol["version"], "body": pol["body"], "exclusions": exclusions, "schedules": schedules,
              "issued_at": datetime.now(timezone.utc).isoformat()}
    return {"bundle": bundle, "signature": crypto.sign(bundle), "key_id": crypto.key_id()}


@router.get("/updates")
def updates(x_device_key: str | None = Header(default=None)):
    _device(x_device_key)
    with db.global_tx() as cur:
        cur.execute("SELECT kind, version, body, signature, key_id, published_at FROM aav.update_bundles "
                    "WHERE revoked_at IS NULL ORDER BY published_at DESC")
        rows = cur.fetchall()
    latest: dict = {}
    for r in rows:
        latest.setdefault(r["kind"], {"kind": r["kind"], "version": r["version"], "body": r["body"],
                                      "signature": r["signature"], "key_id": r["key_id"]})
    return {"latest": latest, "available": [{"kind": r["kind"], "version": r["version"]} for r in rows]}


@router.get("/updates/{kind}/{version}")
def update_version(kind: str, version: str, x_device_key: str | None = Header(default=None)):
    """Fetch a specific verified version (used for rollback)."""
    _device(x_device_key)
    with db.global_tx() as cur:
        cur.execute("SELECT kind, version, body, signature, key_id FROM aav.update_bundles "
                    "WHERE kind = %s AND version = %s AND revoked_at IS NULL", (kind, version))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "no such verified version")
    return row


@router.post("/heartbeat")
def heartbeat(body: HeartbeatIn, x_device_key: str | None = Header(default=None)):
    d = _device(x_device_key)
    if body.protection_status not in ("protected", "degraded", "disabled", "unknown"):
        raise HTTPException(422, "invalid protection_status")
    with db.tenant_tx(d["tenant_id"]) as cur:
        cur.execute("SELECT protection_status FROM aav.devices WHERE id = %s", (d["device_id"],))
        before = cur.fetchone()["protection_status"]
        cur.execute("UPDATE aav.devices SET last_seen_at = now(), agent_version = %s, definitions_version = %s, "
                    "applied_policy_version = %s, protection_status = %s, sensor_health = %s, "
                    "isolation_state = CASE WHEN isolation_expires_at IS NOT NULL AND isolation_expires_at < now() "
                    "THEN 'none' ELSE isolation_state END WHERE id = %s",
                    (body.agent_version, body.definitions_version, body.applied_policy_version,
                     body.protection_status, json.dumps(body.sensor_health), d["device_id"]))
        if before != body.protection_status and body.protection_status in ("degraded", "disabled"):
            notify(cur, d["tenant_id"], "device.degraded", f"Protection {body.protection_status}",
                   {"device_id": str(d["device_id"]), "sensor_health": body.sensor_health})
            audit.record(cur, tenant_id=d["tenant_id"], actor=f"device:{d['device_id']}",
                         action="device.protection_degraded", target=str(d["device_id"]),
                         detail={"status": body.protection_status, "sensor_health": body.sensor_health})
        cur.execute("SELECT count(*) AS n FROM aav.commands WHERE device_id = %s AND status = 'pending' "
                    "AND expires_at > now()", (d["device_id"],))
        pending = cur.fetchone()["n"]
    return {"ok": True, "pending_commands": pending}


def _create_alert(cur, tenant_id, device_id, ev: EventIn, event_id: int) -> str:
    data = ev.data
    uids = [u for u in data.get("evidence_event_uids", []) if isinstance(u, str)]
    cur.execute("SELECT id FROM aav.events WHERE device_id = %s AND event_uid = ANY(%s)", (device_id, uids))
    ids = [r["id"] for r in cur.fetchall()] + [event_id]
    severity = data.get("severity", "medium")
    if severity not in ("low", "medium", "high", "critical"):
        severity = "medium"
    cur.execute("INSERT INTO aav.alerts (tenant_id, device_id, severity, title, rule_id, rule_version, technique, "
                "detected_at, evidence_event_ids, evidence, action_taken) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id",
                (tenant_id, device_id, severity, str(data.get("title", "Detection"))[:300],
                 str(data.get("rule_id", "unknown")), str(data.get("rule_version", "unknown")),
                 data.get("technique"), ev.occurred_at, ids,
                 json.dumps({k: data.get(k) for k in ("sha256", "path", "process", "pid", "cmdline", "matched")
                             if k in data}), data.get("action_taken")))
    alert_id = cur.fetchone()["id"]
    attach_alert_to_incident(cur, tenant_id, alert_id, device_id, severity, str(data.get("title", "Detection")))
    if severity in ("high", "critical"):
        notify(cur, tenant_id, "alert.critical" if severity == "critical" else "alert.high",
               str(data.get("title", "Detection")), {"alert_id": str(alert_id), "device_id": str(device_id)})
    return str(alert_id)


@router.post("/events")
def ingest(batch: EventBatch, x_device_key: str | None = Header(default=None)):
    if len(batch.events) > MAX_BATCH:
        raise HTTPException(413, f"batch larger than {MAX_BATCH} events; split and retry")
    d = _device(x_device_key)
    accepted, duplicates, alerts = 0, 0, []
    with db.tenant_tx(d["tenant_id"]) as cur:
        # non-detection events first so detections can link to evidence in the same batch
        ordered = sorted(batch.events, key=lambda e: e.kind == "detection")
        for ev in ordered:
            cur.execute("INSERT INTO aav.events (tenant_id, device_id, event_uid, kind, occurred_at, data) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (device_id, event_uid) DO NOTHING RETURNING id",
                        (d["tenant_id"], d["device_id"], ev.event_uid, ev.kind, ev.occurred_at, json.dumps(ev.data)))
            row = cur.fetchone()
            if not row:
                duplicates += 1
                continue
            accepted += 1
            if ev.kind == "detection":
                alerts.append(_create_alert(cur, d["tenant_id"], d["device_id"], ev, row["id"]))
            elif ev.kind == "quarantine":
                q = ev.data
                cur.execute("INSERT INTO aav.quarantine_items (tenant_id, device_id, local_id, sha256, original_path, "
                            "detection, rule_version, quarantined_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT (device_id, local_id) DO NOTHING",
                            (d["tenant_id"], d["device_id"], q["local_id"], q["sha256"], q["original_path"],
                             q.get("detection", ""), q.get("rule_version", ""), ev.occurred_at))
            elif ev.kind == "tamper":
                notify(cur, d["tenant_id"], "device.tamper", "Agent tamper attempt",
                       {"device_id": str(d["device_id"]), **ev.data})
    return {"accepted": accepted, "duplicates": duplicates, "alerts": alerts}


@router.get("/commands")
def commands(x_device_key: str | None = Header(default=None)):
    d = _device(x_device_key)
    with db.tenant_tx(d["tenant_id"]) as cur:
        cur.execute("UPDATE aav.commands SET status = 'expired' WHERE device_id = %s AND status IN ('pending','delivered') "
                    "AND expires_at <= now()", (d["device_id"],))
        cur.execute("UPDATE aav.commands SET status = 'delivered' WHERE device_id = %s AND status = 'pending'",
                    (d["device_id"],))
        cur.execute("SELECT id, envelope, signature FROM aav.commands WHERE device_id = %s AND status = 'delivered' "
                    "AND expires_at > now()", (d["device_id"],))
        rows = cur.fetchall()
    return [{"envelope": r["envelope"], "signature": r["signature"]} for r in rows]


@router.post("/commands/{command_id}/ack")
def ack(command_id: UUID, body: AckIn, x_device_key: str | None = Header(default=None)):
    if body.status not in ("acknowledged", "failed"):
        raise HTTPException(422, "status must be acknowledged or failed")
    d = _device(x_device_key)
    with db.tenant_tx(d["tenant_id"]) as cur:
        cur.execute("UPDATE aav.commands SET status = %s, ack_at = now(), result = %s WHERE id = %s AND device_id = %s "
                    "AND status IN ('pending','delivered') RETURNING command_type, params, action_request_id",
                    (body.status, json.dumps(body.result), command_id, d["device_id"]))
        cmd = cur.fetchone()
        if not cmd:
            cur.execute("SELECT status FROM aav.commands WHERE id = %s AND device_id = %s", (command_id, d["device_id"]))
            prior = cur.fetchone()
            if prior:
                return {"ok": True, "duplicate": True, "status": prior["status"]}
            raise HTTPException(404, "unknown command")
        ok = body.status == "acknowledged"
        if cmd["command_type"] == "isolate" and ok:
            cur.execute("UPDATE aav.devices SET isolation_state = 'isolated', isolation_expires_at = now() + "
                        "make_interval(mins => %s) WHERE id = %s", (cmd["params"]["expires_minutes"], d["device_id"]))
        elif cmd["command_type"] == "release_isolation" and ok:
            cur.execute("UPDATE aav.devices SET isolation_state = 'none', isolation_expires_at = NULL WHERE id = %s",
                        (d["device_id"],))
        elif cmd["command_type"] == "restore":
            local_id = cmd["params"]["local_id"]
            scan = body.result.get("rescan", {})
            restored = ok and scan.get("clean") is True
            cur.execute("UPDATE aav.quarantine_items SET status = %s, restore_scan = %s WHERE device_id = %s "
                        "AND local_id = %s", ("restored" if restored else "quarantined", json.dumps(scan),
                                              d["device_id"], local_id))
        if cmd["action_request_id"]:
            cur.execute("SELECT count(*) FILTER (WHERE status IN ('pending','delivered')) AS open, "
                        "count(*) FILTER (WHERE status = 'failed') AS failed FROM aav.commands "
                        "WHERE action_request_id = %s", (cmd["action_request_id"],))
            c = cur.fetchone()
            if c["open"] == 0:
                cur.execute("UPDATE aav.action_requests SET status = %s, updated_at = now() WHERE id = %s",
                            ("failed" if c["failed"] else "completed", cmd["action_request_id"]))
        audit.record(cur, tenant_id=d["tenant_id"], actor=f"device:{d['device_id']}", action="command.ack",
                     target=str(command_id), detail={"type": cmd["command_type"], "status": body.status,
                                                     "result": body.result})
    return {"ok": True}
