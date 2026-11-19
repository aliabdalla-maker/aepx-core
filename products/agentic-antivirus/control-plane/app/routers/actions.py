"""Governed response actions: propose -> (approve) -> dispatch -> acknowledge.

Trace: AI-02, EDR-02, RSP-01..09, AX-06, AX-07, AX-12 (approval single use), OBJ-07, THR-01, DDL-04.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db, governance, harness, rbac
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
    # §3C request contract: a retried submission with the same key returns the original request
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    drill: bool = False   # fixture-driven exercise: shown as a drill in every view and export


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
    lifecycle = {"denied": "denied", "approved": "queued", "proposed": "awaiting_approval"}[status]
    digest = _targets_digest(action.name, body.targets, body.params)
    harness.expire_stale(cur)
    if body.idempotency_key:
        cur.execute("SELECT id, status, lifecycle, targets_digest, policy_decision FROM aav.action_requests "
                    "WHERE idempotency_key = %s", (body.idempotency_key,))
        prior = cur.fetchone()
        if prior:
            if prior["targets_digest"] != digest:
                raise HTTPException(409, "idempotency key already used for a different request")
            return {"id": str(prior["id"]), "status": prior["status"], "lifecycle": prior["lifecycle"],
                    "decision": prior["policy_decision"], "duplicate": True}
    pol = harness.policy(cur)
    decision["policy_version"] = harness.POLICY_VERSION
    decision["runtime_mode"] = pol["mode"]
    f = harness.request_fields(body.idempotency_key, body.evidence_refs, body.drill, pol["mode"])
    cur.execute(
        "INSERT INTO aav.action_requests (tenant_id, incident_id, action_type, targets, targets_digest, params, "
        "reason, proposed_by, status, policy_decision, lifecycle, lifecycle_reason, idempotency_key, expires_at, "
        "policy_version, evidence_refs, runtime_mode, drill) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (tenant_id, body.incident_id, action.name, json.dumps(body.targets), digest, json.dumps(body.params),
         body.reason, proposed_by, status, json.dumps(decision), lifecycle,
         decision.get("reason") if status == "denied" else None, f["idempotency_key"], f["expires_at"],
         f["policy_version"], f["evidence_refs"], f["runtime_mode"], f["drill"]))
    rid = cur.fetchone()["id"]
    if status == "approved" and decision["mode"] == "admin_self":
        cur.execute("INSERT INTO aav.approvals (tenant_id, action_request_id, approver_id, action_type, "
                    "targets_digest, expires_at, approver_roles) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (tenant_id, rid, approver_id, action.name, digest,
                     _now() + timedelta(minutes=settings.approval_ttl_minutes), json.dumps(sorted(proposer_roles))))
    audit.record(cur, tenant_id=tenant_id, actor=proposed_by, action="action.propose", target=str(rid),
                 detail={"action_type": action.name, "targets": body.targets, "decision": decision,
                         "reason": body.reason})
    return {"id": str(rid), "status": status, "lifecycle": lifecycle, "decision": decision}


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
    if result["status"] == "approved" and not result.get("duplicate"):
        try:
            result["dispatch"] = dispatch(UUID(result["id"]), p)
        except HTTPException as exc:
            result["dispatch"] = {"refused": True, "status_code": exc.status_code, "reason": exc.detail}
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
        cur.execute("UPDATE aav.action_requests SET targets = %s, targets_digest = %s, updated_at = now(), "
                    "lifecycle = CASE WHEN lifecycle = 'queued' THEN 'awaiting_approval' ELSE lifecycle END "
                    "WHERE id = %s", (json.dumps(body.targets), digest, request_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.targets_changed",
                     target=str(request_id), detail={"targets": body.targets})
    return {"id": str(request_id), "targets_digest": digest}


@router.post("/{request_id}/approve")
def approve(request_id: UUID, body: DecisionIn, p: Principal = Depends(need("actions.approve"))):
    with db.tenant_tx(p.tenant_id) as cur:
        harness.expire_stale(cur)
        cur.execute("SELECT * FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(404, "not found")
        if req["lifecycle"] == "expired":
            cur.connection.commit()   # keep the Expired lifecycle recorded by the sweep
            raise HTTPException(410, "request expired; propose it again")
        if req["status"] not in ("proposed", "approved"):
            raise HTTPException(409, f"cannot approve in status {req['status']}")
        action = CATALOGUE[req["action_type"]]
        if action.default == "admin_reason" and not (p.roles & ADMIN_ROLES):
            raise HTTPException(403, "an authorised administrator must approve this action")
        if action.name == "apply_traffic_policy" and not rbac.allowed(p.roles, "traffic.approve"):
            raise HTTPException(403, "customer-impacting traffic restrictions need a tenant administrator")
        expires = _now() + timedelta(minutes=settings.approval_ttl_minutes)
        cur.execute("INSERT INTO aav.approvals (tenant_id, action_request_id, approver_id, action_type, "
                    "targets_digest, expires_at, approver_roles) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p.tenant_id, request_id, p.user_id, req["action_type"], req["targets_digest"], expires,
                     json.dumps(sorted(p.roles))))
        aid = cur.fetchone()["id"]
        cur.execute("UPDATE aav.action_requests SET status = 'approved', lifecycle = 'queued', lifecycle_reason = NULL, "
                    "updated_at = now() WHERE id = %s", (request_id,))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="action.approve", target=str(request_id),
                     detail={"approval_id": str(aid), "expires_at": expires.isoformat(), "reason": body.reason,
                             "targets": req["targets"]})
    return {"approval_id": str(aid), "expires_at": expires.isoformat()}


@router.post("/{request_id}/deny")
def deny(request_id: UUID, body: DecisionIn, p: Principal = Depends(need("actions.approve"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.action_requests SET status = 'denied', lifecycle = 'denied', lifecycle_reason = %s, "
                    "updated_at = now() WHERE id = %s AND status IN ('proposed','approved') RETURNING id",
                    (f"denied by approver: {body.reason}"[:500], request_id))
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
        # SEC-08: every exclusion has an approver and a review date (default 90 days).
        cur.execute("SELECT approver_id FROM aav.approvals WHERE action_request_id = %s AND used_at IS NOT NULL "
                    "ORDER BY used_at DESC LIMIT 1", (req["id"],))
        appr = cur.fetchone()
        cur.execute("INSERT INTO aav.exclusions (tenant_id, kind, value, reason, created_by, expires_at, approved_by) "
                    "VALUES (%s,%s,%s,%s,%s, now() + make_interval(days => %s), %s) "
                    "ON CONFLICT (tenant_id, kind, value) DO NOTHING",
                    (tenant_id, req["params"]["kind"], req["params"]["value"], req["reason"], uid,
                     int(req["params"].get("expires_days", 90)), appr["approver_id"] if appr else uid))
        return [{"target": "tenant", "status": "completed"}]
    if t in ("suspend_account", "revoke_sessions"):
        from app.routers.integrations import execute_identity_action
        return [execute_identity_action(cur, tenant_id, req["params"]["integration_id"], t, target)
                for target in req["targets"]]
    if t in ("apply_traffic_policy", "rollback_traffic_policy"):
        from app.routers.threats import execute_traffic_action
        return [execute_traffic_action(cur, tenant_id, t, UUID(target), req["id"]) for target in req["targets"]]
    raise HTTPException(500, f"no executor for {t}")


def _deny(cur, tenant_id, actor, request_id, status: int, reason: str, *, back_to_proposed=False):
    """Record a dispatch denial and refuse. Nothing has been executed and no approval was consumed."""
    if back_to_proposed:
        cur.execute("UPDATE aav.action_requests SET status = 'proposed', lifecycle = 'awaiting_approval', "
                    "lifecycle_reason = %s, updated_at = now() WHERE id = %s", (reason, request_id))
    else:
        cur.execute("UPDATE aav.action_requests SET lifecycle_reason = %s, updated_at = now() WHERE id = %s",
                    (reason, request_id))
    audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch_denied", target=str(request_id),
                 detail={"reason": reason, "policy_version": harness.POLICY_VERSION})
    cur.connection.commit()
    raise HTTPException(status, reason)


def _scan_jobs_for(cur, tenant_id, req, device_id, params: dict, actor: str) -> dict:
    """A run_scan without a job group gets one, so progress and completion are observable independently."""
    if params.get("job_group"):
        return params
    group = params.get("_group") or str(uuid4())
    scan_type = {"quick": "quick", "full": "full", "custom": "targeted"}[params["scan_type"]]
    cur.execute("INSERT INTO aav.scan_jobs (tenant_id, device_id, scan_type, scope, max_seconds, incident_id, "
                "requested_by, group_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (tenant_id, device_id, scan_type, json.dumps(params.get("paths", [])),
                 int(params.get("max_seconds") or 3600), req["incident_id"], actor, group))
    return {**params, "job_group": group, "max_seconds": int(params.get("max_seconds") or 3600)}


def dispatch(request_id: UUID, p: Principal | None = None, *, tenant_id=None, actor: str | None = None) -> dict:
    tenant_id = tenant_id or p.tenant_id
    actor = actor or p.actor
    external = None
    with db.tenant_tx(tenant_id) as cur:
        harness.expire_stale(cur)
        cur.execute("SELECT * FROM aav.action_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if not req:
            raise HTTPException(404, "not found")
        if req["lifecycle"] == "manual_reconciliation":
            raise HTTPException(409, "manual reconciliation required before any retry")
        if req["lifecycle"] == "running" and harness.EXTERNAL_ADAPTERS.get(req["action_type"]):
            # A retry after a lost worker: settle the interrupted attempt with the provider first, never resubmit.
            try:
                state = harness.reconcile(cur, tenant_id, req, actor)
            except harness.Denied as d:
                _deny(cur, tenant_id, actor, request_id, d.status, d.reason)
            if state == "in_progress":
                raise HTTPException(409, "a dispatch is already in progress")
            if state == "manual":
                return {"status": req["status"], "lifecycle": "manual_reconciliation"}
            if state == "receipted":
                harness.set_lifecycle(cur, request_id, "verification_pending", "receipt recovered by reconciliation")
                return {"status": "dispatched", "lifecycle": "verification_pending", "reconciled": True}
            cur.execute("SELECT count(*) AS n FROM aav.action_dispatches WHERE action_request_id = %s AND "
                        "state = 'not_executed'", (request_id,))
            if cur.fetchone()["n"]:
                cur.execute("UPDATE aav.action_requests SET status = 'proposed' WHERE id = %s", (request_id,))
                harness.set_lifecycle(cur, request_id, "awaiting_approval",
                                      "interrupted before the provider received it; approve again to retry")
                return {"status": "proposed", "lifecycle": "awaiting_approval", "reconciled": True, "executed": False}
        if req["status"] in ("dispatched", "completed") or req["lifecycle"] in ("running", "verification_pending",
                                                                                 "verified"):
            cur.execute("SELECT device_id, id, status FROM aav.commands WHERE action_request_id = %s", (request_id,))
            return {"status": req["status"], "lifecycle": req["lifecycle"], "duplicate": True,
                    "commands": [{"device_id": str(r["device_id"]), "command_id": str(r["id"]),
                                  "status": r["status"]} for r in cur.fetchall()]}
        if req["lifecycle"] == "expired":
            _deny(cur, tenant_id, actor, request_id, 410, "request expired before dispatch")
        if req["status"] != "approved":
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch_denied",
                         target=str(request_id), detail={"reason": f"status {req['status']}"})
            raise HTTPException(409, f"not approved (status {req['status']})")
        action = CATALOGUE[req["action_type"]]
        # Scope again at dispatch: every target must still exist in this tenant.
        _resolve_targets(cur, action.target_kind, req["targets"])
        digest = _targets_digest(action.name, req["targets"], req["params"])
        if digest != req["targets_digest"]:
            _deny(cur, tenant_id, actor, request_id, 403, "parameters altered after approval", back_to_proposed=True)
        mode = req["policy_decision"].get("mode")
        appr = None
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
            else:
                problem = harness.approver_still_valid(cur, appr["approver_id"], action)
            if problem:
                _deny(cur, tenant_id, actor, request_id, 403, problem, back_to_proposed=True)
        try:
            route = harness.gate(cur, action, req["targets"])
        except harness.Denied as d:
            _deny(cur, tenant_id, actor, request_id, d.status, d.reason)
        # Re-check AEP-X at execution time: an outage between approval and dispatch fails closed.
        gov = governance.evaluate(action.risk)
        if not gov["allowed"]:
            _deny(cur, tenant_id, actor, request_id, 503, f"AEP-X governance: {gov['reason']}")
        external_adapter = harness.EXTERNAL_ADAPTERS.get(action.name) if route["adapter"] == "live" else None
        if external_adapter:
            try:
                state = harness.reconcile(cur, tenant_id, req, actor)
            except harness.Denied as d:
                _deny(cur, tenant_id, actor, request_id, d.status, d.reason)
            if state == "in_progress":
                raise HTTPException(409, "a dispatch is already in progress")
            if state == "manual":
                return {"status": req["status"], "lifecycle": "manual_reconciliation"}
            if state == "receipted":
                harness.set_lifecycle(cur, request_id, "verification_pending", "receipt recovered by reconciliation")
                cur.execute("UPDATE aav.action_requests SET status = 'dispatched' WHERE id = %s", (request_id,))
                return {"status": "dispatched", "lifecycle": "verification_pending", "reconciled": True}
        if appr:
            cur.execute("UPDATE aav.approvals SET used_at = now() WHERE id = %s", (appr["id"],))
        if route["adapter"] == "simulation":
            outcomes = harness.simulate(cur, tenant_id, req, actor)
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch", target=str(request_id),
                         detail={"outcomes": outcomes, "governance": gov, "mode": "simulation"})
            return {"status": "completed", "lifecycle": "verified", "mode": "simulation", "commands": outcomes}
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
                group = str(uuid4()) if action.name == "run_scan" and not req["params"].get("job_group") else None
                for target in req["targets"]:
                    params = dict(req["params"])
                    if action.name == "isolate_device":
                        cur.execute("SELECT criticality, policy_name FROM aav.devices WHERE id = %s", (target,))
                        dev = cur.fetchone()
                        params["preserve_management"] = True
                        params["criticality"] = dev["criticality"]
                        params["release_procedure"] = "console: release_isolation action, or automatic at expiry"
                    if action.name == "run_scan":
                        params = _scan_jobs_for(cur, tenant_id, req, target, {**params, "_group": group}, actor)
                        params.pop("_group", None)
                    outcomes.append(_command(cur, tenant_id, UUID(target), req, action.endpoint_command, params))
            att = harness.start_attempt(cur, tenant_id, request_id, "endpoint-command")
            harness.finish_attempt(cur, att["id"], "receipted", {"commands": outcomes})
            new_status, lifecycle = "dispatched", "running"
        elif external_adapter:
            att = harness.start_attempt(cur, tenant_id, request_id, external_adapter.name)
            harness.set_lifecycle(cur, request_id, "running")
            cur.execute("UPDATE aav.action_requests SET status = 'dispatched' WHERE id = %s", (request_id,))
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch", target=str(request_id),
                         detail={"adapter": external_adapter.name, "attempt": att["attempt"],
                                 "provider_request_id": att["provider_request_id"], "governance": gov})
            external = (external_adapter, att, req)
        else:
            outcomes = _execute_non_endpoint(cur, tenant_id, req, actor)
            ok = all(o["status"] in ("completed", "active", "rolled_back") for o in outcomes)
            new_status = "completed" if ok else "failed"
            att = harness.start_attempt(cur, tenant_id, request_id, "in-database")
            harness.finish_attempt(cur, att["id"], "receipted" if ok else "failed", {"outcomes": outcomes})
            if ok and req["action_type"] == "add_exclusion":
                cur.execute("SELECT count(*) AS n FROM aav.exclusions WHERE kind = %s AND value = %s",
                            (req["params"]["kind"], req["params"]["value"]))
                present = cur.fetchone()["n"] == 1
                harness.add_verification(cur, tenant_id, request_id, "row_present", True, None,
                                         {"table": "exclusions", "value": req["params"]["value"]})
                cur.execute("UPDATE aav.action_verifications SET status = %s, observed = %s, source = 'server_check', "
                            "observed_at = now() WHERE action_request_id = %s",
                            ("passed" if present else "failed", json.dumps({"value": present}), request_id))
                lifecycle = "verified" if present else "failed"
            elif ok:
                lifecycle = "verification_pending"
            else:
                lifecycle = "failed"
        if external is None:
            cur.execute("UPDATE aav.action_requests SET status = %s, updated_at = now() WHERE id = %s",
                        (new_status, request_id))
            harness.set_lifecycle(cur, request_id, lifecycle,
                                  None if lifecycle != "failed" else "; ".join(o.get("reason", "") for o in outcomes)[:500])
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.dispatch", target=str(request_id),
                         detail={"outcomes": outcomes, "governance": gov, "mode": route["mode"]})
    if external is None:
        return {"status": new_status, "lifecycle": lifecycle, "commands": outcomes}
    # The attempt row is committed: a crash from here on is reconciled against the provider before any retry.
    adapter, att, req = external
    outcomes, failed = [], None
    try:
        for target in req["targets"]:
            outcomes.append(adapter.submit(req["action_type"], target, req["params"],
                                           f"{att['provider_request_id']}:{target}"))
    except harness.AdapterUnavailable as exc:
        failed = f"adapter unavailable: {exc}"
    with db.tenant_tx(tenant_id) as cur:
        if failed:
            harness.finish_attempt(cur, att["id"], "failed" if not outcomes else "unknown", {"partial": outcomes}, failed)
            state = "failed" if not outcomes else "manual_reconciliation"
            cur.execute("UPDATE aav.action_requests SET status = 'failed' WHERE id = %s", (request_id,))
            harness.set_lifecycle(cur, request_id, state, failed)
        else:
            harness.finish_attempt(cur, att["id"], "receipted", {"outcomes": outcomes})
            for target in req["targets"]:
                harness.add_verification(cur, tenant_id, request_id, "provider_status", True, None,
                                         {"target": target, "adapter": adapter.name})
            harness.set_lifecycle(cur, request_id, "verification_pending")
            state = "verification_pending"
        audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.receipt", target=str(request_id),
                     detail={"adapter": adapter.name, "outcomes": outcomes, "error": failed})
    if failed:
        raise HTTPException(502, failed)
    return {"status": "dispatched", "lifecycle": state, "commands": outcomes}


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
