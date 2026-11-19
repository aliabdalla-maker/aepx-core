"""Defensive cybersecurity agentic harness (deployment prompt §3C).

Agents correlate evidence and propose; this deterministic layer owns execution:

  * runtime modes per tenant: SIMULATION (synthetic adapters, no side effects), OBSERVE (read-only actions run,
    everything else stays a proposal), RESPOND (scoped actions for the approved cohort)
  * kill switches (platform env and tenant setting) stop every new response dispatch
  * a request contract (incident, tenant, assets, canonical params digest, requester, policy version, evidence,
    expiry, idempotency key) and an explicit lifecycle:
      proposed -> awaiting_approval -> queued -> running -> verification_pending -> verified
                                                                       | failed | denied | expired
                                                                       | manual_reconciliation
  * dispatch attempts committed before an external adapter is called, reconciled after a lost lease
  * independent verification: read-only probes answered by the agent after the fact, or server-side
    checks, never the command receipt alone

Nothing here trusts a model, a prompt or the browser: tenant and role come from the authenticated
principal and every check runs again at dispatch.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app import audit
from app.config import settings

POLICY_VERSION = "aav-response-policy/1.0.0"
MODES = ("simulation", "observe", "respond")
# Read-only or non-destructive actions that OBSERVE may run for real.
OBSERVE_ACTIONS = {"collect_metadata", "run_scan"}
TERMINAL = {"verified", "failed", "denied", "expired", "manual_reconciliation"}
APPROVAL_SLA_MINUTES = 60


class Denied(Exception):
    """Policy denial: raised before any side effect (no command, no adapter call, no approval consumed)."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- tenant policy
def policy(cur) -> dict:
    cur.execute("SELECT key, value FROM aav.settings WHERE category = 'harness'")
    s = {r["key"]: r["value"] for r in cur.fetchall()}
    mode = s.get("mode") if s.get("mode") in MODES else (
        settings.harness_default_mode if settings.harness_default_mode in MODES else "simulation")
    cohort = s.get("respond_cohort")
    return {"mode": mode, "tenant_kill_switch": s.get("kill_switch") is True,
            "platform_kill_switch": settings.harness_kill_switch,
            "respond_cohort": cohort if isinstance(cohort, list) else ["*"],
            "policy_version": POLICY_VERSION}


def gate(cur, action, targets: list[str], pol: dict | None = None) -> dict:
    """Decide whether a dispatch may proceed and how. Raises Denied; never has side effects."""
    pol = pol or policy(cur)
    if pol["platform_kill_switch"]:
        raise Denied(423, "kill switch on (platform): no new response dispatches")
    if pol["tenant_kill_switch"]:
        raise Denied(423, "kill switch on (tenant): no new response dispatches")
    mode = pol["mode"]
    if mode == "simulation":
        return {"mode": mode, "adapter": "simulation"}
    if mode == "observe" and action.name not in OBSERVE_ACTIONS:
        raise Denied(403, "OBSERVE mode: response actions stay proposals until RESPOND is enabled")
    if mode == "respond" and action.target_kind == "device" and "*" not in pol["respond_cohort"]:
        outside = [t for t in targets if t not in pol["respond_cohort"]]
        if outside and action.name not in OBSERVE_ACTIONS:
            raise Denied(403, f"RESPOND is not enabled for {len(outside)} target device(s) outside the pilot cohort")
    return {"mode": mode, "adapter": "live"}


# ----------------------------------------------------------------------------- lifecycle
def set_lifecycle(cur, request_id, state: str, reason: str | None = None) -> None:
    extra = ", verified_at = now()" if state == "verified" else ""
    cur.execute(f"UPDATE aav.action_requests SET lifecycle = %s, lifecycle_reason = %s, updated_at = now(){extra} "
                "WHERE id = %s", (state, reason, request_id))


def expire_stale(cur) -> int:
    """Requests whose own expiry passed before dispatch become Expired (lazy sweep on every read and write)."""
    cur.execute("UPDATE aav.action_requests SET lifecycle = 'expired', status = 'expired', "
                "lifecycle_reason = 'request expired before dispatch', updated_at = now() "
                "WHERE expires_at IS NOT NULL AND expires_at < now() AND lifecycle IN ('proposed', 'awaiting_approval', "
                "'queued') RETURNING id")
    return len(cur.fetchall())


def request_fields(idempotency_key: str | None, evidence_refs: list[str], drill: bool, mode: str) -> dict:
    return {"idempotency_key": idempotency_key, "evidence_refs": json.dumps(evidence_refs[:50]),
            "expires_at": now() + timedelta(minutes=settings.action_request_ttl_minutes),
            "policy_version": POLICY_VERSION, "runtime_mode": mode, "drill": drill}


def approver_still_valid(cur, approver_id, action) -> str | None:
    """Re-check at dispatch that the approver still holds a role that may approve this action."""
    from app import rbac
    from app.catalogue import ADMIN_ROLES
    cur.execute("SELECT role FROM aav.memberships WHERE user_id = %s", (approver_id,))
    roles = {r["role"] for r in cur.fetchall()}
    if not rbac.allowed(roles, "actions.approve"):
        return "approver no longer authorised"
    if action.default == "admin_reason" and not roles & ADMIN_ROLES:
        return "approver no longer an administrator"
    return None


# ----------------------------------------------------------------------------- adapters
class AdapterUnavailable(Exception):
    pass


class ExternalAdapter:
    """Contract for adapters that change something outside this database (identity, edge, upstream providers).

    submit() must be idempotent on provider_request_id; lookup() returns the provider's record for that id, None
    when the provider has no such request, or raises NotImplementedError when the provider cannot be queried
    (then a lost dispatch goes to manual reconciliation instead of being retried).
    """
    name = "external"

    def submit(self, action_type: str, target: str, params: dict, provider_request_id: str) -> dict:
        raise NotImplementedError

    def lookup(self, provider_request_id: str) -> dict | None:
        raise NotImplementedError

    def observe(self, action_type: str, target: str, params: dict) -> dict:
        """Independent read of the provider state after the action (used for verification)."""
        raise NotImplementedError


# action_type -> adapter. Only adapters that passed a sandbox contract test are registered; none ship in this
# release (integrations.VERIFIED_ADAPTERS is empty), so identity and edge actions report "no adapter".
EXTERNAL_ADAPTERS: dict[str, ExternalAdapter] = {}


def set_adapter(action_type: str, adapter: ExternalAdapter | None) -> None:
    """Test hook and registration point for verified adapters."""
    if adapter is None:
        EXTERNAL_ADAPTERS.pop(action_type, None)
    else:
        EXTERNAL_ADAPTERS[action_type] = adapter


def start_attempt(cur, tenant_id, request_id, adapter: str) -> dict:
    cur.execute("SELECT coalesce(max(attempt), 0) + 1 AS n FROM aav.action_dispatches WHERE action_request_id = %s",
                (request_id,))
    n = cur.fetchone()["n"]
    key = f"{request_id}:{n}"
    cur.execute("INSERT INTO aav.action_dispatches (tenant_id, action_request_id, attempt, adapter, provider_request_id, "
                "lease_owner, lease_expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (tenant_id, request_id, n, adapter, key, f"worker:{uuid.uuid4().hex[:12]}",
                 now() + timedelta(seconds=settings.harness_lease_seconds)))
    return cur.fetchone()


def finish_attempt(cur, attempt_id, state: str, receipt: dict | None = None, error: str | None = None) -> None:
    cur.execute("UPDATE aav.action_dispatches SET state = %s, receipt = %s, error = %s, updated_at = now() "
                "WHERE id = %s", (state, json.dumps(receipt, default=str) if receipt is not None else None, error,
                                  attempt_id))


def reconcile(cur, tenant_id, req, actor: str) -> str:
    """Before any retry: settle attempts left 'running'. Returns 'clear', 'in_progress', 'receipted' or 'manual'."""
    cur.execute("SELECT * FROM aav.action_dispatches WHERE action_request_id = %s AND state = 'running' "
                "ORDER BY attempt", (req["id"],))
    outcome = "clear"
    for att in cur.fetchall():
        if att["lease_expires_at"] > now():
            return "in_progress"
        adapter = EXTERNAL_ADAPTERS.get(req["action_type"])
        try:
            found = adapter.lookup(att["provider_request_id"]) if adapter else None
            if adapter is None:
                raise NotImplementedError
        except NotImplementedError:
            finish_attempt(cur, att["id"], "unknown", error="lease lost; provider cannot be queried")
            set_lifecycle(cur, req["id"], "manual_reconciliation",
                          "a dispatch was interrupted and the provider state cannot be read; reconcile by hand")
            audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.reconcile", target=str(req["id"]),
                         detail={"attempt": att["attempt"], "result": "manual_reconciliation"})
            return "manual"
        except AdapterUnavailable as exc:
            raise Denied(503, f"cannot reconcile: adapter unavailable ({exc})")
        if found:
            finish_attempt(cur, att["id"], "receipted", receipt=found)
            outcome = "receipted"
        else:
            finish_attempt(cur, att["id"], "not_executed", error="lease lost before the provider received it")
        audit.record(cur, tenant_id=tenant_id, actor=actor, action="action.reconcile", target=str(req["id"]),
                     detail={"attempt": att["attempt"], "result": "receipted" if found else "not_executed"})
    return outcome


# ----------------------------------------------------------------------------- verification
def add_verification(cur, tenant_id, request_id, probe: str, expect, device_id=None, args: dict | None = None) -> None:
    cur.execute("INSERT INTO aav.action_verifications (tenant_id, action_request_id, device_id, probe, args, expect) "
                "VALUES (%s,%s,%s,%s,%s,%s)", (tenant_id, request_id, device_id, probe, json.dumps(args or {}),
                                               json.dumps(expect)))


def plan_endpoint_verifications(cur, tenant_id, req, cmd: dict, result: dict) -> None:
    """After a command receipt, record what must be observed independently for this device."""
    t, dev, p = cmd["command_type"], cmd["device_id"], cmd["params"]
    if t == "isolate":
        add_verification(cur, tenant_id, req, "isolation_active", True, dev)
    elif t == "release_isolation":
        add_verification(cur, tenant_id, req, "isolation_active", False, dev)
    elif t == "terminate_process":
        add_verification(cur, tenant_id, req, "pid_absent", True, dev, {"pid": p.get("pid")})
    elif t == "quarantine":
        add_verification(cur, tenant_id, req, "path_absent", True, dev, {"path": p.get("path")})
        if result.get("local_id"):
            add_verification(cur, tenant_id, req, "vault_contains", True, dev, {"local_id": result["local_id"]})
    elif t == "restore":
        add_verification(cur, tenant_id, req, "vault_absent", True, dev, {"local_id": p.get("local_id")})
    elif t == "scan":
        add_verification(cur, tenant_id, req, "scan_job_complete", "complete", dev, {"job_group": p.get("job_group")})
    elif t == "collect_metadata":
        add_verification(cur, tenant_id, req, "metadata_received", True, dev, {"since": cmd["issued_at"].isoformat()})
    elif t == "rollback_update":
        add_verification(cur, tenant_id, req, "definitions_version", p.get("version"), dev, {"kind": p.get("kind")})


AGENT_PROBES = {"isolation_active", "pid_absent", "path_absent", "vault_contains", "vault_absent"}


def pending_probes(cur, device_id) -> list[dict]:
    cur.execute("SELECT id::text AS id, probe, args FROM aav.action_verifications WHERE device_id = %s "
                "AND status = 'pending' AND probe = ANY(%s) AND expires_at > now() ORDER BY created_at LIMIT 20",
                (device_id, list(AGENT_PROBES)))
    return cur.fetchall()


def record_observations(cur, tenant_id, device_id, observations: list[dict]) -> int:
    n = 0
    for o in observations[:50]:
        try:
            vid = UUID(str(o.get("id")))
        except ValueError:
            continue
        cur.execute("SELECT * FROM aav.action_verifications WHERE id = %s AND device_id = %s AND status = 'pending' "
                    "FOR UPDATE", (vid, device_id))
        v = cur.fetchone()
        if not v:
            continue
        value = o.get("value")
        status = "passed" if value == v["expect"] else "failed"
        cur.execute("UPDATE aav.action_verifications SET status = %s, observed = %s, source = 'agent_probe', "
                    "observed_at = now() WHERE id = %s", (status, json.dumps({"value": value}), vid))
        settle(cur, v["action_request_id"])
        n += 1
    return n


def _server_check(cur, v, req: dict) -> tuple[str, object] | None:
    a = v["args"]
    if v["probe"] == "provider_status":
        adapter = EXTERNAL_ADAPTERS.get(req["action_type"])
        if adapter is None:
            return None
        try:
            seen = adapter.observe(req["action_type"], a.get("target"), req["params"])
        except (NotImplementedError, AdapterUnavailable):
            return None
        return ("passed" if seen.get("applied") is True else "failed"), seen
    if v["probe"] == "scan_job_complete":
        cur.execute("SELECT status FROM aav.scan_jobs WHERE group_id::text = %s AND device_id = %s",
                    (str(a.get("job_group")), v["device_id"]))
        j = cur.fetchone()
        if not j or j["status"] in ("queued", "running"):
            return None
        return ("passed" if j["status"] == "complete" else "failed"), j["status"]
    if v["probe"] == "metadata_received":
        cur.execute("SELECT count(*) AS n FROM aav.events WHERE device_id = %s AND kind = 'metadata_collected' "
                    "AND received_at >= %s::timestamptz", (v["device_id"], a.get("since")))
        return ("passed", True) if cur.fetchone()["n"] else None
    if v["probe"] == "definitions_version":
        cur.execute("SELECT definitions_version, agent_version FROM aav.devices WHERE id = %s", (v["device_id"],))
        d = cur.fetchone()
        seen = d["definitions_version"] if a.get("kind") == "detections" else d["agent_version"]
        return ("passed", seen) if seen == v["expect"] else None
    return None


def settle(cur, request_id) -> str | None:
    """Evaluate server-side checks, expire stale probes, and move the request to Verified or Failed."""
    cur.execute("SELECT * FROM aav.action_verifications WHERE action_request_id = %s FOR UPDATE", (request_id,))
    rows = cur.fetchall()
    if not rows:
        return None
    cur.execute("SELECT action_type, params, lifecycle FROM aav.action_requests WHERE id = %s", (request_id,))
    req = cur.fetchone()
    for v in rows:
        if v["status"] != "pending":
            continue
        if v["expires_at"] <= now():
            cur.execute("UPDATE aav.action_verifications SET status = 'expired' WHERE id = %s", (v["id"],))
            v["status"] = "expired"
            continue
        res = _server_check(cur, v, req)
        if res:
            cur.execute("UPDATE aav.action_verifications SET status = %s, observed = %s, source = 'server_check', "
                        "observed_at = now() WHERE id = %s", (res[0], json.dumps({"value": res[1]}, default=str), v["id"]))
            v["status"] = res[0]
    states = {v["status"] for v in rows}
    current = req["lifecycle"]
    if current in TERMINAL:
        return current
    if "failed" in states:
        set_lifecycle(cur, request_id, "failed", "independent verification failed")
        return "failed"
    if "expired" in states:
        set_lifecycle(cur, request_id, "manual_reconciliation", "no independent evidence within 24 hours")
        return "manual_reconciliation"
    if states == {"passed"}:
        set_lifecycle(cur, request_id, "verified")
        cur.execute("UPDATE aav.action_requests SET status = 'completed' WHERE id = %s AND status = 'dispatched'",
                    (request_id,))
        return "verified"
    return None


def settle_open(cur) -> None:
    cur.execute("SELECT id FROM aav.action_requests WHERE lifecycle = 'verification_pending' "
                "AND runtime_mode IS NOT NULL LIMIT 200")
    for r in cur.fetchall():
        settle(cur, r["id"])


# ----------------------------------------------------------------------------- simulation
def simulate(cur, tenant_id, req, actor: str) -> list[dict]:
    """SIMULATION: a synthetic adapter receipt and a synthetic verification. Nothing leaves the database."""
    att = start_attempt(cur, tenant_id, req["id"], "simulation")
    receipt = {"simulated": True, "targets": req["targets"], "action_type": req["action_type"],
               "provider_request_id": att["provider_request_id"]}
    finish_attempt(cur, att["id"], "receipted", receipt)
    add_verification(cur, tenant_id, req["id"], "simulated", True, None, {"note": "synthetic fixture adapter"})
    cur.execute("UPDATE aav.action_verifications SET status = 'passed', observed = '{\"value\": true}', "
                "source = 'simulation', observed_at = now() WHERE action_request_id = %s AND probe = 'simulated'",
                (req["id"],))
    cur.execute("UPDATE aav.action_requests SET drill = true, status = 'completed' WHERE id = %s", (req["id"],))
    set_lifecycle(cur, req["id"], "verified", "simulation: synthetic adapter and verification (drill)")
    return [{"target": t, "status": "simulated"} for t in req["targets"]]
