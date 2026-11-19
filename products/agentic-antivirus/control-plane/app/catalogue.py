"""Typed response-action catalogue (AI-02, RSP-01..10, THR-01, DDL-04).

Every action that can change an endpoint, account or traffic policy is listed here with a
JSON-schema-like parameter contract, a risk class on the AEP-X S0-S4 scale, and its default
permission rule from PRD section 5. Anything not in the catalogue cannot be proposed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionType:
    name: str
    risk: str                 # AEP-X risk class S0..S4
    target_kind: str          # device | quarantine_item | account | session | traffic_policy | tenant
    default: str              # 'auto' | 'approval' | 'admin_reason'
    params: dict              # name -> python type
    required_params: tuple = ()
    endpoint_command: str | None = None   # command type sent to the agent, if any


CATALOGUE: dict[str, ActionType] = {a.name: a for a in [
    # RSP-01: automatic within tenant policy
    ActionType("collect_metadata", "S0", "device", "auto", {"fields": list}, ("fields",), "collect_metadata"),
    ActionType("run_scan", "S0", "device", "auto", {"scan_type": str, "paths": list, "job_group": str,
                                                    "max_seconds": int}, ("scan_type",), "scan"),
    # RSP-02: automatic when enabled by policy for a confirmed known-malware match
    ActionType("quarantine_file", "S1", "device", "auto_if_known_malware",
               {"path": str, "sha256": str, "known_malware": bool}, ("path", "sha256"), "quarantine"),
    # RSP-03: approval by default
    ActionType("terminate_process", "S2", "device", "approval", {"pid": int, "image_sha256": str}, ("pid",),
               "terminate_process"),
    ActionType("isolate_device", "S2", "device", "approval", {"expires_minutes": int}, ("expires_minutes",),
               "isolate"),
    ActionType("release_isolation", "S1", "device", "approval", {}, (), "release_isolation"),
    # RSP-04: authorised administrator + recorded reason
    ActionType("restore_file", "S2", "quarantine_item", "admin_reason", {}, (), "restore"),
    ActionType("add_exclusion", "S2", "tenant", "admin_reason", {"kind": str, "value": str}, ("kind", "value")),
    # THR-01: scoped approval for account suspension or session revocation
    ActionType("suspend_account", "S2", "account", "approval", {"integration_id": str}, ("integration_id",)),
    ActionType("revoke_sessions", "S2", "session", "approval", {"integration_id": str}, ("integration_id",)),
    # DDL-04: approval for new customer-impacting restrictions; rollback always allowed by approver
    ActionType("apply_traffic_policy", "S2", "traffic_policy", "approval", {}, ()),
    ActionType("rollback_traffic_policy", "S1", "traffic_policy", "approval", {}, ()),
    # OPS-02: rollback agent/detections to a verified version
    ActionType("rollback_update", "S1", "device", "approval", {"kind": str, "version": str}, ("kind", "version"),
               "rollback_update"),
]}

ADMIN_ROLES = {"tenant_admin", "it_admin", "msp_operator"}


def validate_params(action: ActionType, params: dict) -> None:
    unknown = set(params) - set(action.params)
    if unknown:
        raise ValueError(f"unknown parameters: {sorted(unknown)}")
    for name in action.required_params:
        if name not in params:
            raise ValueError(f"missing parameter: {name}")
    for name, value in params.items():
        expected = action.params[name]
        if expected is int and isinstance(value, bool):
            raise ValueError(f"{name} must be int")
        if not isinstance(value, expected):
            raise ValueError(f"{name} must be {expected.__name__}")
    if action.name == "isolate_device" and not (1 <= params["expires_minutes"] <= 7 * 24 * 60):
        raise ValueError("expires_minutes must be between 1 and 10080")
    if action.name == "run_scan" and params["scan_type"] not in ("quick", "full", "custom"):
        raise ValueError("scan_type must be quick, full or custom")
    if action.name == "add_exclusion" and params["kind"] not in ("path", "sha256"):
        raise ValueError("kind must be path or sha256")
    if action.name == "rollback_update" and params["kind"] not in ("detections", "agent"):
        raise ValueError("kind must be detections or agent")
