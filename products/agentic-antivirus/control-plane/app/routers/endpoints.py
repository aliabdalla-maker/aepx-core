"""Console: device inventory, enrolment, policies, scan schedules, exclusions, quarantine,
signed update publication.

Trace: OPS-01 (inventory, sensor health, protection status, policy assignment, stale
definitions / disabled sensors / outdated policies), USR-02, AV-01 (scheduled scans),
AV-02 (review & restore), RSP-04, OPS-02, THR-06, ARC-03.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db
from app.deps import Principal, need, tenant_principal
from app import rbac
from app.routers.actions import ProposeIn, propose, dispatch

router = APIRouter(prefix="/v1", tags=["endpoints"])

STALE_DEFINITIONS_HOURS = 24
STALE_HEARTBEAT_MINUTES = 30

POLICY_SCHEMA_KEYS = {
    "on_access": bool, "on_execute": bool, "on_download": bool, "auto_quarantine_known": bool,
    "behaviour_rules": bool, "block_suspicious_scripts": bool, "removable_media": str, "event_buffer_mb": int,
    "collect_file_contents": bool, "allowed_management_hosts": list, "isolation_allowed": bool,
    "cpu_limit_percent": int, "tamper_protection": bool, "url_protection": bool,
}


class TokenIn(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=10000)
    expires_hours: int = Field(default=24, ge=1, le=24 * 30)


class DevicePatch(BaseModel):
    policy_name: str | None = Field(default=None, max_length=100)
    criticality: str | None = None
    owner_user_id: UUID | None = None


class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern="^[a-z0-9_-]+$")
    body: dict


class ScheduleIn(BaseModel):
    policy_name: str
    scan_type: str
    cron: str = Field(pattern=r"^(\S+\s+){4}\S+$")


class ScanIn(BaseModel):
    # Empty list means "all active devices in the tenant" (resolved in run_scan).
    device_ids: list[str] = Field(default_factory=list, max_length=500)
    scan_type: str = "quick"


class ReviewIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class BundleIn(BaseModel):
    kind: str
    version: str = Field(min_length=1, max_length=50)
    body: dict


def validate_policy(body: dict) -> None:
    unknown = set(body) - set(POLICY_SCHEMA_KEYS)
    if unknown:
        raise HTTPException(422, f"unknown policy keys: {sorted(unknown)}")
    for k, v in body.items():
        t = POLICY_SCHEMA_KEYS[k]
        if (t is int and isinstance(v, bool)) or not isinstance(v, t):
            raise HTTPException(422, f"{k} must be {t.__name__}")
    if body.get("removable_media", "audit") not in ("allow", "audit", "block"):
        raise HTTPException(422, "removable_media must be allow, audit or block")
    if not 1 <= body.get("event_buffer_mb", 64) <= 4096:
        raise HTTPException(422, "event_buffer_mb out of range")


@router.post("/enrollment-tokens", status_code=201)
def create_enrollment_token(body: TokenIn, p: Principal = Depends(need("devices.enrol"))):
    token = crypto.new_token()
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.enrollment_tokens (tenant_id, token_hash, max_uses, expires_at, created_by) "
                    "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (p.tenant_id, crypto.token_hash(token), body.max_uses,
                     datetime.now(timezone.utc) + timedelta(hours=body.expires_hours), p.user_id))
        tid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="enrollment_token.create", target=str(tid),
                     detail={"max_uses": body.max_uses})
    return {"id": str(tid), "token": token}


@router.get("/devices")
def devices(limit: int = 200, offset: int = 0, p: Principal = Depends(tenant_principal)):
    own_only = not rbac.allowed(p.roles, "devices.read")
    if own_only:
        p.require("self.devices.read")
    limit = max(1, min(limit, 1000))
    with db.global_tx() as cur:
        cur.execute("SELECT version, published_at FROM aav.update_bundles WHERE kind = 'detections' "
                    "AND revoked_at IS NULL ORDER BY published_at DESC LIMIT 1")
        latest_def = cur.fetchone()
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT name, max(version) AS v FROM aav.policies GROUP BY name")
        latest_pol = {r["name"]: r["v"] for r in cur.fetchall()}
        cur.execute("SELECT id, hostname, os, os_version, agent_version, criticality, policy_name, "
                    "applied_policy_version, definitions_version, sensor_health, protection_status, isolation_state, "
                    "isolation_expires_at, enrolled_at, last_seen_at, owner_user_id FROM aav.devices "
                    "WHERE retired_at IS NULL AND (NOT %s OR owner_user_id = %s) ORDER BY hostname LIMIT %s OFFSET %s",
                    (own_only, p.user_id, limit, offset))
        rows = cur.fetchall()
    now = datetime.now(timezone.utc)
    for r in rows:
        issues = []
        if latest_def and r["definitions_version"] != latest_def["version"] and \
                now - latest_def["published_at"] > timedelta(hours=STALE_DEFINITIONS_HOURS):
            issues.append("stale_definitions")
        elif latest_def and r["definitions_version"] != latest_def["version"]:
            issues.append("definitions_update_pending")
        if any(v is False or v == "disabled" for v in (r["sensor_health"] or {}).values()):
            issues.append("sensor_disabled")
        if r["policy_name"] in latest_pol and r["applied_policy_version"] != latest_pol[r["policy_name"]]:
            issues.append("outdated_policy")
        if not r["last_seen_at"] or now - r["last_seen_at"] > timedelta(minutes=STALE_HEARTBEAT_MINUTES):
            issues.append("not_reporting")
        if r["protection_status"] in ("degraded", "disabled"):
            issues.append(f"protection_{r['protection_status']}")
        r["issues"] = issues
    return rows


@router.patch("/devices/{device_id}")
def patch_device(device_id: UUID, body: DevicePatch, p: Principal = Depends(need("devices.write"))):
    if body.criticality and body.criticality not in ("standard", "critical"):
        raise HTTPException(422, "invalid criticality")
    with db.tenant_tx(p.tenant_id) as cur:
        if body.policy_name:
            cur.execute("SELECT 1 FROM aav.policies WHERE name = %s", (body.policy_name,))
            if not cur.fetchone():
                raise HTTPException(404, "policy not found")
        cur.execute("UPDATE aav.devices SET policy_name = COALESCE(%s, policy_name), criticality = COALESCE(%s, "
                    "criticality), owner_user_id = COALESCE(%s, owner_user_id) WHERE id = %s RETURNING id",
                    (body.policy_name, body.criticality, body.owner_user_id, device_id))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="device.update", target=str(device_id),
                     detail=body.model_dump(exclude_none=True, mode="json"))
    return {"id": str(device_id)}


@router.delete("/devices/{device_id}")
def retire_device(device_id: UUID, p: Principal = Depends(need("devices.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.devices SET retired_at = now() WHERE id = %s AND retired_at IS NULL RETURNING id",
                    (device_id,))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="device.retire", target=str(device_id))
    return {"retired": True}


@router.get("/policies")
def policies(p: Principal = Depends(need("policies.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT id, name, version, body, key_id, created_by, created_at FROM aav.policies "
                    "ORDER BY name, version DESC")
        return cur.fetchall()


@router.post("/policies", status_code=201)
def publish_policy(body: PolicyIn, p: Principal = Depends(need("policies.write"))):
    validate_policy(body.body)
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT COALESCE(max(version), 0) + 1 AS v FROM aav.policies WHERE name = %s", (body.name,))
        version = cur.fetchone()["v"]
        signed = {"tenant_id": str(p.tenant_id), "name": body.name, "version": version, "body": body.body}
        cur.execute("INSERT INTO aav.policies (tenant_id, name, version, body, signature, key_id, created_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p.tenant_id, body.name, version, json.dumps(body.body), crypto.sign(signed), crypto.key_id(),
                     p.user_id))
        pid = cur.fetchone()["id"]
        if body.body.get("auto_quarantine_known") is not None:
            cur.execute("INSERT INTO aav.settings (tenant_id, category, key, value, updated_by) VALUES "
                        "(%s,'agent_policies','auto_quarantine_known',%s,%s) ON CONFLICT (tenant_id, category, key) "
                        "DO UPDATE SET value = EXCLUDED.value, version = aav.settings.version + 1, updated_at = now()",
                        (p.tenant_id, json.dumps(body.body["auto_quarantine_known"]), p.user_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="policy.publish", target=str(pid),
                     detail={"name": body.name, "version": version, "body": body.body})
    return {"id": str(pid), "name": body.name, "version": version}


@router.get("/scan-schedules")
def schedules(p: Principal = Depends(need("policies.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.scan_schedules ORDER BY created_at")
        return cur.fetchall()


@router.post("/scan-schedules", status_code=201)
def add_schedule(body: ScheduleIn, p: Principal = Depends(need("scans.schedule"))):
    if body.scan_type not in ("quick", "full"):
        raise HTTPException(422, "scan_type must be quick or full")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.scan_schedules (tenant_id, policy_name, scan_type, cron, created_by) "
                    "VALUES (%s,%s,%s,%s,%s) RETURNING id", (p.tenant_id, body.policy_name, body.scan_type, body.cron,
                                                            p.user_id))
        sid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="scan_schedule.create", target=str(sid),
                     detail=body.model_dump())
    return {"id": str(sid)}


@router.delete("/scan-schedules/{sid}")
def delete_schedule(sid: UUID, p: Principal = Depends(need("scans.schedule"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("DELETE FROM aav.scan_schedules WHERE id = %s RETURNING id", (sid,))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="scan_schedule.delete", target=str(sid))
    return {"deleted": True}


@router.post("/scans", status_code=201)
def run_scan(body: ScanIn, p: Principal = Depends(need("scans.run"))):
    """On-demand scan through the action catalogue (auto for one device, approval for many)."""
    with db.tenant_tx(p.tenant_id) as cur:
        targets = [str(d) for d in body.device_ids]
        if not targets:
            # Empty device_ids means "all active devices in the tenant".
            cur.execute("SELECT id FROM aav.devices WHERE retired_at IS NULL ORDER BY id LIMIT 501")
            targets = [str(r["id"]) for r in cur.fetchall()]
            if not targets:
                raise HTTPException(422, "no active devices to scan")
            if len(targets) > 500:
                raise HTTPException(422, "more than 500 active devices; specify device_ids explicitly")
        res = propose(cur, tenant_id=p.tenant_id, body=ProposeIn(action_type="run_scan", targets=targets,
                                                                 params={"scan_type": body.scan_type}),
                      proposed_by=p.actor, proposer_roles=p.roles, approver_id=p.user_id)
    if res["status"] == "approved":
        res["dispatch"] = dispatch(UUID(res["id"]), p)
    return res


@router.get("/exclusions")
def exclusions(p: Principal = Depends(need("policies.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.exclusions ORDER BY created_at")
        return cur.fetchall()


@router.delete("/exclusions/{eid}")
def delete_exclusion(eid: UUID, p: Principal = Depends(need("exclusions.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("DELETE FROM aav.exclusions WHERE id = %s RETURNING kind, value", (eid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="exclusion.delete", target=str(eid),
                     detail=row)
    return {"deleted": True}


@router.get("/quarantine")
def quarantine(status: str | None = None, p: Principal = Depends(tenant_principal)):
    own_only = not rbac.allowed(p.roles, "quarantine.read")
    if own_only:
        p.require("quarantine.request_review")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT q.*, d.hostname FROM aav.quarantine_items q JOIN aav.devices d ON d.id = q.device_id "
                    "WHERE (%s::text IS NULL OR q.status = %s) AND (NOT %s OR d.owner_user_id = %s) "
                    "ORDER BY q.quarantined_at DESC LIMIT 500", (status, status, own_only, p.user_id))
        return cur.fetchall()


@router.post("/quarantine/{qid}/request-review")
def request_review(qid: UUID, body: ReviewIn, p: Principal = Depends(need("quarantine.request_review"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.quarantine_items SET status = 'review_requested', review_reason = %s "
                    "WHERE id = %s AND status = 'quarantined' RETURNING id", (body.reason, qid))
        if not cur.fetchone():
            raise HTTPException(409, "item not found or not in quarantine")
        from app.routers.incidents import notify
        notify(cur, p.tenant_id, "quarantine.review_requested", "Quarantine review requested",
               {"quarantine_id": str(qid), "reason": body.reason})
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="quarantine.review_requested",
                     target=str(qid), detail={"reason": body.reason})
    return {"status": "review_requested"}


@router.post("/quarantine/{qid}/restore", status_code=201)
def restore(qid: UUID, body: ReviewIn, p: Principal = Depends(need("quarantine.restore"))):
    """RSP-04 + AV-02: authorised administrator, recorded reason, fresh scan on the endpoint
    before the file is released; outcome lands in the audit trail via the command ack."""
    with db.tenant_tx(p.tenant_id) as cur:
        res = propose(cur, tenant_id=p.tenant_id, body=ProposeIn(action_type="restore_file", targets=[str(qid)],
                                                                 params={}, reason=body.reason),
                      proposed_by=p.actor, proposer_roles=p.roles, approver_id=p.user_id)
    if res["status"] == "approved":
        res["dispatch"] = dispatch(UUID(res["id"]), p)
    return res


@router.post("/updates", status_code=201)
def publish_bundle(body: BundleIn, p: Principal = Depends(need("updates.publish"))):
    """Sign and publish a detection or agent bundle. Only tenant admins of the operator tenant
    should hold updates.publish in production; content is validated before signing."""
    from app.detections import validate_bundle
    if body.kind not in ("detections", "agent"):
        raise HTTPException(422, "kind must be detections or agent")
    try:
        validate_bundle(body.kind, body.body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    signed = {"kind": body.kind, "version": body.version, "body": body.body}
    with db.global_tx() as cur:
        cur.execute("INSERT INTO aav.update_bundles (kind, version, body, signature, key_id, published_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (kind, version) DO NOTHING RETURNING id",
                    (body.kind, body.version, json.dumps(body.body), crypto.sign(signed), crypto.key_id(), p.user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "version already published")
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="update.publish", target=str(row["id"]),
                     detail={"kind": body.kind, "version": body.version})
    return {"id": str(row["id"]), "kind": body.kind, "version": body.version}


@router.post("/updates/{kind}/{version}/revoke")
def revoke_bundle(kind: str, version: str, p: Principal = Depends(need("updates.publish"))):
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.update_bundles SET revoked_at = now() WHERE kind = %s AND version = %s "
                    "AND revoked_at IS NULL RETURNING id", (kind, version))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="update.revoke", target=f"{kind}@{version}")
    return {"revoked": True}
