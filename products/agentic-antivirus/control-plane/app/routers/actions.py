"""Governed response actions: propose -> (approve) -> dispatch -> acknowledge.

Trace: AI-02, EDR-02, RSP-01..09, AX-06, AX-07, AX-12 (approval single use), OBJ-07, THR-01, DDL-04.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db, governance, rbac
from app.catalogue import ADMIN_ROLES, CATALOGUE, validate_params
from app.config import settings
from app.deps import Principal, need

router = APIRouter(prefix="/v1/actions", tags=["actions"])


class ProposeIn(BaseModel):
    action_type: str
    targets: list[str] = Field(min_length=1, max_length=1000)
    params: dict = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)
    incident_id: UUID | None = None


class TargetsPatch(BaseModel):
    targets: list[str] = Field(min_length=1, max_length=1000)


class DecisionIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _targets_digest(action_type: str, targets: list[str], params: dict) -> str:
    return crypto.digest({"action": action_type, "targets": sorted(targets), "params": params})


def _resolve_targets(cur, kind: str, targets: list[str]) -> None:
    """Every target must exist in the current tenant. RLS hides other tenants, so a cross-tenant
    id is indistinguishable from a missing one and is denied the same way."""
    table = {"device": "aav.devices", "quarantine_item": "aav.quarantine_items",
             "traffic_policy": "aav.traffic_policies"}.get(kind)
    if table is None:
        return
    try:
        ids = [str(UUID(t)) for t in targets]
    except ValueError:
        raise HTTPException(422, "targets must be ids")
    cur.execute(f"SELECT count(*) AS n FROM {table} WHERE id = ANY(%s::uuid[])", (ids,))
    if cur.fetchone()["n"] != len(set(ids)):
        raise HTTPException(404, "target not found in tenant")


def _known_malware(cur, sha256: str) -> bool:
    cur.execute("SELECT body FROM aav.update_bundles WHERE kind = 'detections' AND revoked_at IS NULL "
                "ORDER BY published_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        return False
    return any(s.get("sha256") == sha256 for s in row["body"].get("hash_signatures", []))


def _tenant_auto_quarantine(cur, tenant_id) -> bool:
    cur.execute("SELECT value FROM aav.settings WHERE category = 'agent_policies' AND key = 'auto_quarantine_known'")
    row = cur.fetchone()
    return bool(row and row["value"] is True)


def decide(cur, *, tenant_id, action, targets: list[str], params: dict, proposer_roles: set[str],
           proposed_by: str, reason: str) -> dict:
    """Product policy engine. Returns the decision; never executes anything."""
    multi = action.target_kind == "device" and len(targets) > 1
    if action.default == "auto" and not multi:
        mode = "auto"
    elif action.default == "auto_if_known_malware" and not multi and _tenant_auto_quarantine(cur, tenant_id) \
            and _known_malware(cur, params.get("sha256", "")):
        mode = "auto"
    elif action.default == "admin_reason":
        if len(reason.strip()) < 3:
            return {"allowed": False, "mode": "denied", "reason": "a recorded reason is required"}
        mode = "admin_self" if proposed_by.startswith("user:") and proposer_roles & ADMIN_ROLES else "approval"
    else:
        mode = "approval"
    gov = governance.evaluate(action.risk)
    if not gov["allowed"]:
        return {"allowed": False, "mode": "denied", "reason": f"AEP-X governance: {gov['reason'] or 'denied'}",
                "governance": gov}
    return {"allowed": True, "mode": mode, "multi_endpoint": multi, "risk": action.risk, "governance": gov}


def propose(cur, *, tenant_id, body: ProposeIn, proposed_by: str, proposer_roles: set[str],
            approver_id=None) -> dict:
    action = CATALOGUE.get(body.action_type)
    if action is None:
        raise HTTPException(422, "action not in catalogue")
    try:
        validate_params(action, body.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _resolve_targets(cur, action.target_kind, body.targets)
    decision = decide(cur, tenant_id=tenant_id, action=action, targets=body.targets, params=body.params,
                      proposer_roles=proposer_roles, proposed_by=proposed_by, reason=body.reason)
    status = "denied" if not decision["allowed"] else ("approved" if decision["mode"] in ("auto", "admin_self")
                                                       else "proposed")
    digest = _targets_digest(action.name, body.targets, body.params)
    cur.execute(
        "INSERT INTO aav.action_requests (tenant_id, incident_id, action_type, targets, targets_digest, params, "
        "reason, proposed_by, status, policy_decision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (tenant_id, body.incident_id, action.name, json.dumps(body.targets), digest, json.dumps(body.params),
         body.reason, proposed_by, status, json.dumps(decision)))
    rid = cur.fetchone()["id"]
    if status == "approved" and decision["mode"] == "admin_self":
        cur.execute("INSERT INTO aav.approvals (tenant_id, action_request_id, approver_id, action_type, "
                    "targets_digest, expires_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (tenant_id, rid, approver_id, action.name, digest,
                     _now() + timedelta(minutes=settings.approval_ttl_minutes)))
    audit.record(cur, tenant_id=tenant_id, actor=proposed_by, action="action.propose", target=str(rid),
                 detail={"action_type": action.name, "targets": body.targets, "decision": decision,
                         "reason": body.reason})
    return {"id": str(rid), "status": status, "decision": decision}


@router.get("/catalogue")
def catalogue(p: Principal = Depends(need("actions.read"))):
    return [{"name": a.name, "risk": a.risk, "target_kind": a.target_kind, "default": a.default,
             "params": {k: v.__name__ for k, v in a.params.items()}, "required": list(a.required_params)}
            for a in CATALOGUE.values()]


@router.post("", status_code=201)
def propose_action(body: ProposeIn, p: Principal = Depends(need("actions.propose"))):
    with db.tenant_tx(p.tenant_id) as cur:
        result = propose(cur, tenant_id=p.tenant_id, body=body, proposed_by=p.actor, proposer_roles=p.roles,
                         approver_id=p.user_id)
    if result["status"] == "approved":
        result["dispatch"] = dispatch(UUID(result["id"]), p)
    return result


@router.get("")
def list_actions(status: str | None = None, p: Principal = Depends(need("actions.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.action_requests WHERE (%s::text IS NULL OR status = %s) "
                    "ORDER BY created_at DESC LIMIT 500", (status, status))
        return cur.fetchall()


@router.patch("/{request_id}/targets")
def change_targets(request_id: UUID, body: TargetsPatch, p: Principal = Depends(need("actions.propose"))):
    """Targets may change while pending, but any existing approval stays bound to the old
    target digest, so dispatch will refuse until a new approval is given."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(404, "not found")
        if req["status"] not in ("proposed", "approved"):
            raise HTTPException(409, f"cannot change targets in status {req['status']}")
        action = CATALOGUE[req["action_type"]]
        _resolve_targets(cur, action.target_kind, body.targets)
        digest = _targets_digest(action.name, body.targets, req["params"])
        cur.execute("UPDATE aav.action_requests SET targets = %s, targets_digest = %s, updated_at = now() "
                    "WHERE id = %s", (json.dumps(body.targets), digest, request_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.targets_changed",
                     target=str(request_id), detail={"targets": body.targets})
    return {"id": str(request_id), "targets_digest": digest}


@router.post("/{request_id}/approve")
def approve(request_id: UUID, body: DecisionIn, p: Principal = Depends(need("actions.approve"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(404, "not found")
        if req["status"] not in ("proposed", "approved"):
            raise HTTPException(409, f"cannot approve in status {req['status']}")
        action = CATALOGUE[req["action_type"]]
        if action.default == "admin_reason" and not (p.roles & ADMIN_ROLES):
            raise HTTPException(403, "an authorised administrator must approve this action")
        if action.name == "apply_traffic_policy" and not rbac.allowed(p.roles, "traffic.approve"):
            raise HTTPException(403, "customer-impacting traffic restrictions need a tenant administrator")
        expires = _now() + timedelta(minutes=settings.approval_ttl_minutes)
        cur.execute("INSERT INTO aav.approvals (tenant_id, action_request_id, approver_id, action_type, "
                    "targets_digest, expires_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p.tenant_id, request_id, p.user_id, req["action_type"], req["targets_digest"], expires))
        aid = cur.fetchone()["id"]
        cur.execute("UPDATE aav.action_requests SET status = 'approved', updated_at = now() WHERE id = %s",
                    (request_id,))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.approve", target=str(request_id),
                     detail={"approval_id": str(aid), "expires_at": expires.isoformat(), "reason": body.reason,
                             "targets": req["targets"]})
    return {"approval_id": str(aid), "expires_at": expires.isoformat()}


@router.post("/{request_id}/deny")
def deny(request_id: UUID, body: DecisionIn, p: Principal = Depends(need("actions.approve"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.action_requests SET status = 'denied', updated_at = now() "
                    "WHERE id = %s AND status IN ('proposed','approved') RETURNING id", (request_id,))
        if not cur.fetchone():
            raise HTTPException(404, "not found or not pending")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.deny", target=str(request_id),
                     detail={"reason": body.reason})
    return {"status": "denied"}


def _command(cur, tenant_id, device_id, req, ctype: str, params: dict) -> dict:
    key = f"{req['id']}:{device_id}"
    cur.execute("SELECT id, status FROM aav.commands WHERE device_id = %s AND idempotency_key = %s",
                (device_id, key))
    existing = cur.fetchone()
    if existing:
        return {"device_id": str(device_id), "command_id": str(existing["id"]), "status": existing["status"],
                "duplicate": True}
    issued = _now()
    expires = issued + timedelta(minutes=settings.command_ttl_minutes)
    cur.execute("SELECT gen_random_uuid() AS id")
    cid = cur.fetchone()["id"]
    envelope = {"command_id": str(cid), "tenant_id": str(tenant_id), "device_id": str(device_id), "type": ctype,
                "params": params, "idempotency_key": key, "issued_at": issued.isoformat(),
                "expires_at": expires.isoformat()}
    cur.execute("INSERT INTO aav.commands (id, tenant_id, device_id, action_request_id, idempotency_key, "
                "command_type, params, envelope, signature, issued_at, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, tenant_id, device_id, req["id"], key, ctype, json.dumps(params), json.dumps(envelope),
                 crypto.sign(envelope), issued, expires))
    return {"device_id": str(device_id), "command_id": str(cid), "status": "pending", "duplicate": False}


def _execute_non_endpoint(cur, tenant_id, req, actor: str) -> list[dict]:
    t = req["action_type"]
    if t == "add_exclusion":
        uid = actor.split(":", 1)[1] if actor.startswith("user:") else None
        cur.execute("INSERT INTO aav.exclusions (tenant_id, kind, value, reason, created_by) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id, kind, value) DO NOTHING",
                    (tenant_id, req["params"]["kind"], req["params"]["value"], req["reason"], uid))
        return [{"target": "tenant", "status": "completed"}]
    if t in ("suspend_account", "revoke_sessions"):
        from app.routers.integrations import execute_identity_action
        return [execute_identity_action(cur, tenant_id, req["params"]["integration_id"], t, target)
                for target in req["targets"]]
    if t in ("apply_traffic_policy", "rollback_traffic_policy"):
        from app.routers.threats import execute_traffic_action
        return [execute_traffic_action(cur, tenant_id, t, UUID(target), req["id"]) for target in req["targets"]]
    raise HTTPException(500, f"no executor for {t}")


def dispatch(request_id: UUID, p: Principal | None = None, *, tenant_id=None, actor: str | None = None) -> dict:
    tenant_id = tenant_id or p.tenant_id
    actor = actor or p.actor
    with db.tenant_tx(tenant_id) as cur:
        cur.execute("SELECT * FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(404, "not found")
        if req["status"] in ("dispatched", "completed"):
            cur.execute("SELECT device_id, id, status FROM aav.commands WHERE action_request_id = %s", (request_id,))
            return {"status": req["status"], "duplicate": True,
                    "commands": [{"device_id": str(r["device_id"]), "command_id": str(r["id"]),
                                  "status": r["status"]} for r in cur.fetchall()]}
        if req["status"] != "approved":
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch_denied",
                         target=str(request_id), detail={"reason": f"status {req['status']}"})
            raise HTTPException(409, f"not approved (status {req['status']})")
        action = CATALOGUE[req["action_type"]]
        mode = req["policy_decision"].get("mode")
        if mode != "auto":
            cur.execute("SELECT * FROM aav.approvals WHERE action_request_id = %s AND used_at IS NULL "
                        "ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (request_id,))
            appr = cur.fetchone()
            problem = None
            if not appr:
                problem = "missing approval"
            elif appr["expires_at"] <= _now():
                problem = "approval expired"
            elif appr["targets_digest"] != req["targets_digest"]:
                problem = "targets changed after approval"
            elif appr["action_type"] != req["action_type"]:
                problem = "approval bound to a different action"
            if problem:
                cur.execute("UPDATE aav.action_requests SET status = 'proposed', updated_at = now() WHERE id = %s",
                            (request_id,))
                audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch_denied",
                             target=str(request_id), detail={"reason": problem})
                # commit the denial record, then refuse
                cur.connection.commit()
                raise HTTPException(403, problem)
            cur.execute("UPDATE aav.approvals SET used_at = now() WHERE id = %s", (appr["id"],))
        # Re-check AEP-X at execution time: an outage between approval and dispatch fails closed.
        gov = governance.evaluate(action.risk)
        if not gov["allowed"]:
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch_denied",
                         target=str(request_id), detail={"reason": gov["reason"]})
            cur.connection.commit()
            raise HTTPException(503, f"AEP-X governance: {gov['reason']}")
        if action.endpoint_command:
            outcomes = []
            if action.target_kind == "quarantine_item":
                cur.execute("SELECT id, device_id, local_id, status FROM aav.quarantine_items WHERE id = ANY(%s::uuid[])",
                            (req["targets"],))
                for q in cur.fetchall():
                    cur.execute("UPDATE aav.quarantine_items SET status = 'restore_approved' WHERE id = %s", (q["id"],))
                    outcomes.append(_command(cur, tenant_id, q["device_id"], req, action.endpoint_command,
                                             {"local_id": q["local_id"], "require_clean_rescan": True}))
            else:
                for target in req["targets"]:
                    params = dict(req["params"])
                    if action.name == "isolate_device":
                        cur.execute("SELECT criticality, policy_name FROM aav.devices WHERE id = %s", (target,))
                        dev = cur.fetchone()
                        params["preserve_management"] = True
                        params["criticality"] = dev["criticality"]
                        params["release_procedure"] = "console: release_isolation action, or automatic at expiry"
                    outcomes.append(_command(cur, tenant_id, UUID(target), req, action.endpoint_command, params))
            new_status = "dispatched"
        else:
            outcomes = _execute_non_endpoint(cur, tenant_id, req, actor)
            new_status = "completed" if all(o["status"] in ("completed", "active", "rolled_back")
                                             for o in outcomes) else "failed"
        cur.execute("UPDATE aav.action_requests SET status = %s, updated_at = now() WHERE id = %s",
                    (new_status, request_id))
        audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch", target=str(request_id),
                     detail={"outcomes": outcomes, "governance": gov})
    return {"status": new_status, "commands": outcomes}


@router.post("/{request_id}/dispatch")
def dispatch_action(request_id: UUID, p: Principal = Depends(need("actions.propose"))):
    return dispatch(request_id, p)


@router.get("/{request_id}/outcomes")
def outcomes(request_id: UUID, p: Principal = Depends(need("actions.read"))):
    """RSP-05: outcome per device."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT c.device_id, d.hostname, c.command_type, c.status, c.ack_at, c.result "
                    "FROM aav.commands c JOIN aav.devices d ON d.id = c.device_id "
                    "WHERE c.action_request_id = %s ORDER BY d.hostname", (request_id,))
        return cur.fetchall()
