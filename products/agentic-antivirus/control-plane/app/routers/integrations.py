"""Integration endpoints and inbound signal ingestion.

Trace: INT-01..11, AX-09 (maturity: verified_live / test_only / stub / unavailable, default
unavailable, no stubs in production), FN-07 (simulation labelled), SEC-01, SEC-02, THR-01..10,
DDOS-01..05 (provider alerts), DDL-02 (notify within 60 s of receipt), REC-01 (backup checks).

Provider-specific adapters are not bundled: until an adapter for a named provider has passed
its sandbox contract test, its integration can be at most `test_only`, and executing actions
against it (suspend account, revoke sessions, apply traffic policy, backup check) returns a
failed outcome with the reason rather than pretending to succeed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db
from app.deps import Principal, need
from app.netpolicy import EgressDenied, check_endpoint
from app.routers.incidents import notify

router = APIRouter(prefix="/v1", tags=["integrations"])

# Adapters that have passed a sandbox contract test, keyed by (signal_kind, provider).
# Empty in this release: see docs/STATUS.md and register item B-06.
VERIFIED_ADAPTERS: dict[tuple[str, str], object] = {}

INGEST_CATEGORIES = {
    "identity": {"unusual_sign_in", "repeated_failures", "privilege_change", "suspicious_session"},
    "dns": {"malicious_domain", "authoritative_unavailable", "suspicious_query"},
    "firewall": {"malicious_destination", "lateral_movement", "port_scan", "blocked_connection"},
    "waf": {"injection", "broken_access_control", "automated_abuse", "sensitive_endpoint_misuse", "app_layer_flood"},
    "api_gateway": {"injection", "broken_access_control", "automated_abuse", "sensitive_endpoint_misuse",
                    "app_layer_flood"},
    "ddos": {"volumetric_flood", "reflection_amplification", "protocol_exhaustion", "app_layer_flood",
             "mitigation_started", "mitigation_ended"},
    "cdn": {"app_layer_flood", "origin_bypass", "origin_unhealthy"},
    "load_balancer": {"connection_saturation", "packet_rate", "origin_unhealthy"},
    "backup": {"backup_failed", "backup_verified"},
    "dlp": {"unusual_access", "unusual_transfer"},
    "cloud_audit": {"risky_config_change", "suspicious_key_use", "privilege_escalation"},
    "email": {"phishing_report", "malicious_url"},
    "url_reputation": {"malicious_url"},
    "physical": {"device_theft", "premises_alert"},
    "vulnerability": {"known_exposure"},
}


class IntegrationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    signal_kind: str
    protocol: str
    endpoint: str = Field(default="", max_length=2000)
    config: dict = Field(default_factory=dict)
    secret_ref: str | None = Field(default=None, max_length=200)


class PromoteIn(BaseModel):
    maturity: str
    provider: str = Field(min_length=1, max_length=100)
    evidence: dict


class IngestIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    category: str
    severity: str
    observed_at: datetime
    asset: str | None = Field(default=None, max_length=500)
    device_hostname: str | None = Field(default=None, max_length=255)
    device_ip: str | None = Field(default=None, max_length=64)
    user_ref: str | None = Field(default=None, max_length=320)
    confirmed: bool = False
    data: dict = Field(default_factory=dict)


@router.get("/integrations")
def list_integrations(p: Principal = Depends(need("integrations.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT id, name, signal_kind, protocol, endpoint, config, secret_ref IS NOT NULL AS has_secret, "
                    "maturity, enabled, public_port_approved, last_health, created_at FROM aav.integrations ORDER BY name")
        return cur.fetchall()


@router.post("/integrations", status_code=201)
def create_integration(body: IntegrationIn, p: Principal = Depends(need("integrations.write"))):
    if body.signal_kind not in INGEST_CATEGORIES and body.signal_kind not in ("smtp", "other"):
        raise HTTPException(422, "unknown signal_kind")
    if "password" in json.dumps(body.config).lower() or "secret" in json.dumps(body.config).lower():
        raise HTTPException(422, "credentials belong in the secret store; pass secret_ref instead")
    webhook_secret = crypto.new_token()
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.integrations (tenant_id, name, signal_kind, protocol, endpoint, config, secret_ref, "
                    "webhook_secret_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (p.tenant_id, body.name, body.signal_kind, body.protocol, body.endpoint, json.dumps(body.config),
                     body.secret_ref, crypto.token_hash(webhook_secret)))
        iid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.create", target=str(iid),
                     detail={"name": body.name, "signal_kind": body.signal_kind, "protocol": body.protocol})
    return {"id": str(iid), "maturity": "unavailable", "enabled": False,
            "webhook_url": f"/v1/ingest/{iid}", "webhook_secret": webhook_secret}


@router.post("/integrations/{iid}/health")
def health_check(iid: UUID, p: Principal = Depends(need("integrations.write"))):
    """Egress-policy check of the configured endpoint (no data sent)."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT endpoint, config FROM aav.integrations WHERE id = %s", (iid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if not row["endpoint"]:
            result = {"ok": True, "mode": "inbound_webhook_only", "checked_at": datetime.now(timezone.utc).isoformat()}
        else:
            try:
                info = check_endpoint(row["endpoint"], allow_private=bool(row["config"].get("private_network_approved")))
                result = {"ok": True, **info, "checked_at": datetime.now(timezone.utc).isoformat()}
            except EgressDenied as exc:
                result = {"ok": False, "reason": str(exc), "checked_at": datetime.now(timezone.utc).isoformat()}
        cur.execute("UPDATE aav.integrations SET last_health = %s WHERE id = %s", (json.dumps(result), iid))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.health", target=str(iid),
                     detail=result)
    return result


@router.post("/integrations/{iid}/maturity")
def set_maturity(iid: UUID, body: PromoteIn, p: Principal = Depends(need("integrations.write"))):
    """Raise or lower maturity. verified_live requires a registered verified adapter for the
    provider plus recorded sandbox-contract, credential and policy evidence (AX-09)."""
    if body.maturity not in ("verified_live", "test_only", "stub", "unavailable"):
        raise HTTPException(422, "invalid maturity")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT signal_kind, secret_ref FROM aav.integrations WHERE id = %s", (iid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if body.maturity == "verified_live":
            needed = {"sandbox_contract_passed", "credential_verified", "policy_reviewed"}
            if (row["signal_kind"], body.provider) not in VERIFIED_ADAPTERS:
                raise HTTPException(409, f"no verified adapter for {row['signal_kind']}/{body.provider}")
            if not row["secret_ref"] or not all(body.evidence.get(k) is True for k in needed):
                raise HTTPException(409, f"evidence required: {sorted(needed)} and a secret_ref")
        cur.execute("UPDATE aav.integrations SET maturity = %s, enabled = %s, config = config || %s WHERE id = %s",
                    (body.maturity, body.maturity in ("verified_live", "test_only"),
                     json.dumps({"provider": body.provider}), iid))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.maturity", target=str(iid),
                     detail=body.model_dump())
    return {"id": str(iid), "maturity": body.maturity}


@router.post("/integrations/{iid}/approve-public-port")
def approve_public_port(iid: UUID, p: Principal = Depends(need("settings.write_sensitive"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.integrations SET public_port_approved = true WHERE id = %s RETURNING id", (iid,))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.public_port_approved",
                     target=str(iid))
    return {"approved": True}


def _attribute_device(cur, hostname: str | None, ip: str | None):
    if hostname:
        cur.execute("SELECT id FROM aav.devices WHERE lower(hostname) = lower(%s) AND retired_at IS NULL", (hostname,))
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]["id"]
    if ip:
        cur.execute("SELECT DISTINCT device_id FROM aav.events WHERE data->>'local_ip' = %s "
                    "AND occurred_at > now() - interval '7 days'", (ip,))
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]["device_id"]
    return None


@router.post("/ingest/{iid}", status_code=202)
def ingest(iid: UUID, body: IngestIn, x_aav_webhook_secret: str | None = Header(default=None)):
    with db.global_tx() as cur:
        cur.execute("SELECT * FROM aav.integration_for_webhook(%s)", (iid,))
        integ = cur.fetchone()
    if not integ or not x_aav_webhook_secret or not crypto.hmac_ok(integ["webhook_secret_hash"], x_aav_webhook_secret):
        raise HTTPException(401, "unknown integration or bad secret")
    if not integ["enabled"] or integ["maturity"] not in ("verified_live", "test_only"):
        raise HTTPException(409, f"integration not enabled (maturity {integ['maturity']})")
    kind = integ["signal_kind"]
    if body.category not in INGEST_CATEGORIES.get(kind, set()):
        raise HTTPException(422, f"category '{body.category}' not valid for {kind}")
    if body.severity not in ("low", "medium", "high", "critical"):
        raise HTTPException(422, "invalid severity")
    tid = integ["tenant_id"]
    simulation = integ["maturity"] != "verified_live"
    with db.tenant_tx(tid) as cur:
        device_id = _attribute_device(cur, body.device_hostname, body.device_ip)
        data = dict(body.data, simulation=simulation)
        cur.execute("INSERT INTO aav.external_alerts (tenant_id, integration_id, signal_kind, category, severity, asset, "
                    "device_id, user_ref, confirmed, external_id, observed_at, data) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (integration_id, external_id) DO NOTHING "
                    "RETURNING id", (tid, iid, kind, body.category, body.severity, body.asset, device_id, body.user_ref,
                                     body.confirmed, body.external_id, body.observed_at, json.dumps(data)))
        row = cur.fetchone()
        if not row:
            return {"duplicate": True}
        xid = row["id"]
        incident_id = None
        if device_id:
            cur.execute("SELECT DISTINCT a.incident_id FROM aav.alerts a JOIN aav.incidents i ON i.id = a.incident_id "
                        "WHERE a.device_id = %s AND i.status <> 'resolved' LIMIT 1", (device_id,))
            r = cur.fetchone()
            incident_id = r["incident_id"] if r else None
        if not incident_id and body.asset and kind in ("ddos", "cdn", "load_balancer", "waf", "api_gateway", "dns"):
            cur.execute("SELECT DISTINCT x.incident_id FROM aav.external_alerts x JOIN aav.incidents i ON i.id = "
                        "x.incident_id WHERE x.asset = %s AND i.status <> 'resolved' LIMIT 1", (body.asset,))
            r = cur.fetchone()
            incident_id = r["incident_id"] if r else None
        if not incident_id and body.severity in ("high", "critical"):
            category = {"ddos": "ddos", "cdn": "ddos", "load_balancer": "ddos", "identity": "identity",
                        "email": "phishing"}.get(kind, kind)
            cur.execute("INSERT INTO aav.incidents (tenant_id, title, severity, category) VALUES (%s,%s,%s,%s) "
                        "RETURNING id", (tid, f"{kind}: {body.category}" + (f" on {body.asset}" if body.asset else ""),
                                         body.severity, category))
            incident_id = cur.fetchone()["id"]
        if incident_id:
            cur.execute("UPDATE aav.external_alerts SET incident_id = %s WHERE id = %s", (incident_id, xid))
            cur.execute("UPDATE aav.incidents SET updated_at = now() WHERE id = %s", (incident_id,))
        if kind == "ddos" and body.category in ("mitigation_started", "mitigation_ended") and body.asset:
            cur.execute("UPDATE aav.protected_assets SET mitigation_active = %s WHERE value = %s",
                        (body.category == "mitigation_started", body.asset))
        if body.severity == "critical":
            notify(cur, tid, f"{kind}.critical", f"Critical {kind} alert: {body.category}",
                   {"external_alert_id": str(xid), "asset": body.asset, "simulation": simulation,
                    "incident_id": str(incident_id) if incident_id else None})
            cur.execute("UPDATE aav.external_alerts SET notified_at = now() WHERE id = %s", (xid,))
        audit.record(cur, tenant_id=tid, actor=f"integration:{iid}", action="signal.ingest", target=str(xid),
                     detail={"kind": kind, "category": body.category, "device_id": str(device_id) if device_id else None,
                             "simulation": simulation})
    return {"id": str(xid), "device_id": str(device_id) if device_id else None,
            "incident_id": str(incident_id) if incident_id else None, "simulation": simulation}


def execute_identity_action(cur, tenant_id, integration_id: str, action: str, target: str) -> dict:
    cur.execute("SELECT signal_kind, maturity, enabled, config FROM aav.integrations WHERE id = %s", (integration_id,))
    integ = cur.fetchone()
    if not integ or integ["signal_kind"] != "identity":
        return {"target": target, "status": "failed", "reason": "identity integration not found in tenant"}
    adapter = VERIFIED_ADAPTERS.get(("identity", integ["config"].get("provider", "")))
    if integ["maturity"] != "verified_live" or not integ["enabled"] or adapter is None:
        return {"target": target, "status": "failed",
                "reason": f"no verified_live identity adapter (maturity {integ['maturity']}); nothing was changed"}
    return adapter.execute(action, target)  # pragma: no cover - no verified adapters ship yet


class BackupCheckIn(BaseModel):
    integration_id: UUID


@router.post("/recovery/{item_id}/verify-backup")
def verify_backup(item_id: UUID, body: BackupCheckIn, p: Principal = Depends(need("recovery.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT signal_kind, maturity, enabled, config FROM aav.integrations WHERE id = %s",
                    (body.integration_id,))
        integ = cur.fetchone()
        adapter = VERIFIED_ADAPTERS.get(("backup", (integ or {}).get("config", {}).get("provider", "")))
        if not integ or integ["signal_kind"] != "backup" or integ["maturity"] != "verified_live" or adapter is None:
            evidence = {"verified": None, "reason": "no verified_live backup adapter; availability unknown",
                        "checked_at": datetime.now(timezone.utc).isoformat()}
        else:  # pragma: no cover - no verified adapters ship yet
            evidence = adapter.verify_backup(item_id)
        cur.execute("UPDATE aav.recovery_items SET backup_verified = %s, backup_evidence = %s, updated_at = now() "
                    "WHERE id = %s RETURNING id", (evidence["verified"], json.dumps(evidence), item_id))
        if not cur.fetchone():
            raise HTTPException(404, "recovery item not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.verify_backup", target=str(item_id),
                     detail=evidence)
    return evidence
