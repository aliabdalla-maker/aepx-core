"""Integration endpoints and inbound signal ingestion.

Trace: INT-01..11, AX-09 (maturity: verified_live / test_only / stub / unavailable, default
unavailable, no stubs in production), FN-07 (simulation labelled), SEC-01, SEC-02, THR-01..10,
DDOS-01..05 (provider alerts), DDL-02 (notify within 60 s of receipt), REC-01 (backup checks).

Provider adapters (app/providers, B-06) talk to the providers' real APIs. An integration becomes verified_live only
when its adapter exists, its own stored credential passed a live check (verify-credentials) in the last 24 hours,
and sandbox-contract and policy-review evidence is recorded. Until then actions against it (suspend account,
revoke sessions, apply traffic policy, backup check) return a failed outcome with the reason; provider refusals
are reported as failures too, never as success.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db, providers
from app.deps import Principal, need
from app.netpolicy import EgressDenied, check_endpoint
from app.routers.incidents import notify

router = APIRouter(prefix="/v1", tags=["integrations"])

# Adapters whose provider contract is covered by tests, keyed by (signal_kind, provider) — app/providers.
VERIFIED_ADAPTERS = providers.REGISTRY
CREDENTIAL_CHECK_MAX_AGE_S = 24 * 3600
OUTBOUND_KINDS = ("messaging", "crm", "itsm")
TEST_TRANSPORT = None          # tests only: an httpx transport standing in for the providers' APIs


_SECRET_PREFIXES = ("sk-", "sk_", "pk_", "rk_", "ghp_", "gho_", "github_pat_", "xox", "AKIA", "ASIA", "AIza", "ya29.",
                    "eyJ", "glpat-", "-----BEGIN")


def looks_like_secret(value: str) -> bool:
    """A secret reference is a short name (e.g. "cloudflare-prod"); tokens and keys are long and high-entropy."""
    v = value.strip()
    if v.startswith(_SECRET_PREFIXES):
        return True
    if len(v) >= 32 and " " not in v:
        classes = sum(any(f(c) for c in v) for f in (str.islower, str.isupper, str.isdigit))
        return classes >= 2 and len(set(v)) >= 16
    return False


def build_adapter(cur, integ: dict):
    """Instantiate the adapter for an integration row (needs id, tenant_id, signal_kind, endpoint, config)."""
    cls = VERIFIED_ADAPTERS.get((integ["signal_kind"], (integ.get("config") or {}).get("provider", "")))
    if cls is None:
        raise providers.ProviderError(f"no adapter for {integ['signal_kind']}/{(integ.get('config') or {}).get('provider')}")
    cur.execute("SELECT nonce, ciphertext FROM aav.integration_secrets WHERE integration_id = %s", (integ["id"],))
    row = cur.fetchone()
    secret = crypto.open_secret(bytes(row["nonce"]), bytes(row["ciphertext"]),
                                f"{integ['tenant_id']}:{integ['id']}") if row else ""
    kw = {"http": __import__("httpx").Client(transport=TEST_TRANSPORT), "check_egress": False} if TEST_TRANSPORT else {}
    if cls is providers.REGISTRY[("backup", "s3")] or integ["signal_kind"] in OUTBOUND_KINDS:
        return cls(integ.get("config") or {}, secret, **kw)
    return cls(integ.get("config") or {}, secret, endpoint=integ.get("endpoint") or "", **kw)

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


class SecretIn(BaseModel):
    value: str = Field(min_length=1, max_length=20000)


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
    if body.signal_kind not in INGEST_CATEGORIES and body.signal_kind not in ("smtp", "other") + OUTBOUND_KINDS:
        raise HTTPException(422, "unknown signal_kind")
    if "password" in json.dumps(body.config).lower() or "secret" in json.dumps(body.config).lower():
        raise HTTPException(422, "credentials belong in the secret store; pass secret_ref instead")
    if body.secret_ref and looks_like_secret(body.secret_ref):
        # Audit 27 Nov 2026: an API key was typed into "Secret reference" and stored in clear text.
        raise HTTPException(422, "This looks like a real credential, not a reference to one. Leave Secret reference "
                                 "empty, create the integration, then store the credential with "
                                 "PUT /v1/integrations/{id}/secret (it is encrypted and never shown again). "
                                 "If you pasted a live key, revoke it with the provider.")
    if body.endpoint:
        from urllib.parse import urlparse
        u = urlparse(body.endpoint)
        from app.netpolicy import ALLOWED_SCHEMES
        if u.scheme not in ALLOWED_SCHEMES | {"mqtt"} or not (u.hostname or (u.scheme == "postgresql" and "host=" in u.query)):
            raise HTTPException(422, "Endpoint must be a full address with a TLS scheme, e.g. https://api.example.com "
                                     f"(allowed: {', '.join(sorted(ALLOWED_SCHEMES))}); leave it empty for inbound webhooks")
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


@router.put("/integrations/{iid}/secret", status_code=204)
def store_secret(iid: UUID, body: SecretIn, p: Principal = Depends(need("integrations.write"))):
    """Write-only: the credential is encrypted at rest and never returned by any endpoint."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT id FROM aav.integrations WHERE id = %s", (iid,))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        nonce, ct = crypto.seal_secret(body.value, f"{p.tenant_id}:{iid}")
        cur.execute("INSERT INTO aav.integration_secrets (integration_id, tenant_id, nonce, ciphertext, updated_by) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (integration_id) DO UPDATE SET nonce = excluded.nonce, "
                    "ciphertext = excluded.ciphertext, updated_by = excluded.updated_by, updated_at = now()",
                    (iid, p.tenant_id, nonce, ct, p.actor))
        cur.execute("UPDATE aav.integrations SET secret_ref = %s, config = config - 'credential_check' WHERE id = %s",
                    (f"sealed:{iid}", iid))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.secret_stored", target=str(iid),
                     detail={"bytes": len(body.value)})


@router.post("/integrations/{iid}/rotate-webhook-secret")
def rotate_webhook_secret(iid: UUID, p: Principal = Depends(need("integrations.write"))):
    """Issue a new inbound webhook secret. The old one stops working immediately (webhook, gRPC and every other
    transport that authenticates with it). The new secret is returned once and only its hash is stored."""
    webhook_secret = crypto.new_token()
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.integrations SET webhook_secret_hash = %s WHERE id = %s RETURNING id",
                    (crypto.token_hash(webhook_secret), iid))
        if not cur.fetchone():
            raise HTTPException(404, "not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.webhook_secret_rotated",
                     target=str(iid), detail={})
    return {"id": str(iid), "webhook_url": f"/v1/ingest/{iid}", "webhook_secret": webhook_secret}


@router.post("/integrations/{iid}/verify-credentials")
def verify_credentials(iid: UUID, p: Principal = Depends(need("integrations.write"))):
    """Live check of the stored credential against the provider's API (read-only call)."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.integrations WHERE id = %s", (iid,))
        integ = cur.fetchone()
        if not integ:
            raise HTTPException(404, "not found")
        now = datetime.now(timezone.utc)
        try:
            result = {**build_adapter(cur, integ).health(), "checked_at": now.isoformat()}
        except providers.ProviderError as exc:
            result = {"ok": False, "reason": str(exc), "checked_at": now.isoformat()}
        cur.execute("UPDATE aav.integrations SET last_health = %s, config = config || %s WHERE id = %s",
                    (json.dumps(result), json.dumps({"credential_check": {"ok": result["ok"], "at": now.timestamp()}}),
                     iid))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="integration.verify_credentials",
                     target=str(iid), detail=result)
    return result


@router.post("/integrations/{iid}/maturity")
def set_maturity(iid: UUID, body: PromoteIn, p: Principal = Depends(need("integrations.write"))):
    """Raise or lower maturity. verified_live requires a registered verified adapter for the
    provider plus recorded sandbox-contract, credential and policy evidence (AX-09)."""
    if body.maturity not in ("verified_live", "test_only", "stub", "unavailable"):
        raise HTTPException(422, "invalid maturity")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT signal_kind, secret_ref, config FROM aav.integrations WHERE id = %s", (iid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "not found")
        if body.maturity == "verified_live":
            needed = {"sandbox_contract_passed", "policy_reviewed"}
            if (row["signal_kind"], body.provider) not in VERIFIED_ADAPTERS:
                raise HTTPException(409, f"no verified adapter for {row['signal_kind']}/{body.provider}")
            if row["config"].get("provider") not in (None, body.provider):
                raise HTTPException(409, "provider differs from the one whose credential was checked")
            if not row["secret_ref"] or not all(body.evidence.get(k) is True for k in needed):
                raise HTTPException(409, f"evidence required: {sorted(needed)} and a stored credential")
            chk = row["config"].get("credential_check") or {}
            if not chk.get("ok") or datetime.now(timezone.utc).timestamp() - chk.get("at", 0) > CREDENTIAL_CHECK_MAX_AGE_S:
                raise HTTPException(409, "credential not verified live in the last 24 h: "
                                         "POST /v1/integrations/{id}/verify-credentials")
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
    return ingest_signal(iid, integ, body)


def authenticate_ingest(iid: UUID, presented_secret: str | None) -> dict:
    """Shared by the webhook, gRPC and other push transports: returns the integration row or raises 401."""
    with db.global_tx() as cur:
        cur.execute("SELECT * FROM aav.integration_for_webhook(%s)", (iid,))
        integ = cur.fetchone()
    if not integ or not presented_secret or not crypto.hmac_ok(integ["webhook_secret_hash"], presented_secret):
        raise HTTPException(401, "unknown integration or bad secret")
    return integ


def ingest_signal(iid: UUID, integ: dict, body: IngestIn) -> dict:
    """Canonical signal ingestion for every transport (webhook, gRPC, SQL and IMAP pollers)."""
    if not integ["enabled"] or integ["maturity"] not in ("verified_live", "test_only"):
        raise HTTPException(409, f"integration not enabled (maturity {integ['maturity']})")
    kind = integ["signal_kind"]
    if body.category not in INGEST_CATEGORIES.get(kind, set()):
        raise HTTPException(422, f"category '{body.category}' not valid for {kind}")
    if body.severity not in ("low", "medium", "high", "critical"):
        raise HTTPException(422, "invalid severity")
    tid = integ["tenant_id"]
    simulation = integ["maturity"] != "verified_live"
    from app.routers.agent import normalise_time
    body.observed_at, body.data = normalise_time(body.observed_at, body.data)
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
    cur.execute("SELECT * FROM aav.integrations WHERE id = %s", (integration_id,))
    integ = cur.fetchone()
    if not integ or integ["signal_kind"] != "identity":
        return {"target": target, "status": "failed", "reason": "identity integration not found in tenant"}
    adapter = VERIFIED_ADAPTERS.get(("identity", integ["config"].get("provider", "")))
    if integ["maturity"] != "verified_live" or not integ["enabled"] or adapter is None:
        return {"target": target, "status": "failed",
                "reason": f"no verified_live identity adapter (maturity {integ['maturity']}); nothing was changed"}
    try:
        return build_adapter(cur, integ).execute(action, target)
    except providers.ProviderError as exc:
        return {"target": target, "status": "failed", "reason": str(exc)}


class BackupCheckIn(BaseModel):
    integration_id: UUID


@router.post("/recovery/{item_id}/verify-backup")
def verify_backup(item_id: UUID, body: BackupCheckIn, p: Principal = Depends(need("recovery.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.integrations WHERE id = %s", (body.integration_id,))
        integ = cur.fetchone()
        adapter = VERIFIED_ADAPTERS.get(("backup", (integ or {}).get("config", {}).get("provider", "")))
        if not integ or integ["signal_kind"] != "backup" or integ["maturity"] != "verified_live" or adapter is None:
            evidence = {"verified": None, "reason": "no verified_live backup adapter; availability unknown",
                        "checked_at": datetime.now(timezone.utc).isoformat()}
        else:
            try:
                evidence = build_adapter(cur, integ).verify_backup(item_id)
            except providers.ProviderError as exc:
                evidence = {"verified": False, "reason": str(exc), "checked_at": datetime.now(timezone.utc).isoformat()}
        cur.execute("UPDATE aav.recovery_items SET backup_verified = %s, backup_evidence = %s, updated_at = now() "
                    "WHERE id = %s RETURNING id", (evidence["verified"], json.dumps(evidence), item_id))
        if not cur.fetchone():
            raise HTTPException(404, "recovery item not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="recovery.verify_backup", target=str(item_id),
                     detail=evidence)
    return evidence


class UrlCheckIn(BaseModel):
    url: str = Field(min_length=4, max_length=4000)


@router.post("/url-reputation")
def url_reputation(body: UrlCheckIn, p: Principal = Depends(need("alerts.read"))):
    """SEC-02: the signed detection bundle's reputation list plus every verified_live url_reputation provider."""
    from app.detections import current_engine
    eng = current_engine()
    det = eng.check_url(body.url) if eng else None
    results = [{"source": f"detection_bundle:{eng.version}" if eng else "detection_bundle:none",
                "malicious": bool(det) if eng else None, "threat": det.title if det else None}]
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.integrations WHERE signal_kind = 'url_reputation' AND maturity = 'verified_live' "
                    "AND enabled")
        for integ in cur.fetchall():
            try:
                results.append(build_adapter(cur, integ).lookup(body.url))
            except providers.ProviderError as exc:
                results.append({"source": integ["config"].get("provider"), "malicious": None, "error": str(exc)})
        answered = [r for r in results if r.get("malicious") is not None]
        verdict = "malicious" if any(r.get("malicious") for r in results) else ("not_listed" if answered else "unknown")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="url.reputation_check", target=body.url[:200],
                     detail={"verdict": verdict, "sources": [r.get("source") for r in results]})
    return {"url": body.url, "verdict": verdict, "results": results}


def deliver_outbound(tenant_id, kind: str, title: str, body: dict) -> list[dict]:
    """INT-03: send one notification to every verified_live messaging/CRM/ITSM integration of the tenant.
    Called after commit (see incidents.notify); failures are recorded on the integration, never raised."""
    out = []
    with db.tenant_tx(tenant_id) as cur:
        cur.execute("SELECT * FROM aav.integrations WHERE signal_kind = ANY(%s) AND maturity = 'verified_live' "
                    "AND enabled", (list(OUTBOUND_KINDS),))
        for integ in cur.fetchall():
            if kind not in (integ["config"].get("kinds") or [kind]):      # optional per-integration filter
                continue
            try:
                res = {"ok": True, **build_adapter(cur, integ).send(kind, title, body)}
            except providers.ProviderError as exc:
                res = {"ok": False, "reason": str(exc)[:300]}
            res["checked_at"] = datetime.now(timezone.utc).isoformat()
            cur.execute("UPDATE aav.integrations SET last_health = %s WHERE id = %s", (json.dumps(res), integ["id"]))
            out.append({"integration_id": str(integ["id"]), **res})
    return out
