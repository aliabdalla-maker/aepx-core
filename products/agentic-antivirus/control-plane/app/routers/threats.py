"""DDoS and availability protection, service objectives, traffic policies, per-tenant coverage.

Trace: DDOS-01 (asset inventory, alert on uncovered assets, mitigation state), DDOS-02..04
(provider/LB/WAF/DNS signals ingested via integrations.py), DDL-01 (100% accounting of public
endpoints with provider/owner/policy/capacity/exceptions), DDL-02, DDL-03 (per-service
thresholds defined before testing), DDL-04 (standing policies independent of console/AI;
approval for new customer-impacting restrictions; rollback logged), THR-00 (coverage records).
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import audit, db
from app.deps import Principal, need
from app.routers.actions import ProposeIn, propose
from app.routers.incidents import notify
from app.routers.integrations import VERIFIED_ADAPTERS

router = APIRouter(prefix="/v1", tags=["threats"])


class AssetIn(BaseModel):
    kind: str
    value: str = Field(min_length=1, max_length=500)
    service: str = Field(min_length=1, max_length=200)
    service_owner: str = Field(default="", max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    mitigation_policy: str | None = Field(default=None, max_length=500)
    capacity_assumptions: str | None = Field(default=None, max_length=2000)
    exception_note: str | None = Field(default=None, max_length=2000)
    public: bool = True


class SloIn(BaseModel):
    service: str
    availability_pct: float = Field(gt=0, le=100)
    latency_p95_ms: int = Field(gt=0)
    success_rate_pct: float = Field(gt=0, le=100)


class TrafficIn(BaseModel):
    service: str
    control: str
    config: dict
    customer_impacting: bool = True
    standing: bool = False
    reason: str = Field(min_length=3, max_length=2000)


def _uncovered(a: dict) -> bool:
    return a["public"] and not (a["provider"] and a["mitigation_policy"]) and not a["exception_note"]


@router.get("/assets")
def assets(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.protected_assets ORDER BY service, value")
        rows = cur.fetchall()
    for r in rows:
        r["covered"] = not _uncovered(r)
    return rows


@router.post("/assets", status_code=201)
def upsert_asset(body: AssetIn, p: Principal = Depends(need("assets.write"))):
    if body.kind not in ("ip", "hostname", "dns_zone"):
        raise HTTPException(422, "kind must be ip, hostname or dns_zone")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.protected_assets (tenant_id, kind, value, service, service_owner, provider, "
                    "mitigation_policy, capacity_assumptions, exception_note, public) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, kind, value) DO UPDATE SET "
                    "service = EXCLUDED.service, service_owner = EXCLUDED.service_owner, provider = EXCLUDED.provider, "
                    "mitigation_policy = EXCLUDED.mitigation_policy, capacity_assumptions = "
                    "EXCLUDED.capacity_assumptions, exception_note = EXCLUDED.exception_note, public = EXCLUDED.public "
                    "RETURNING *", (p.tenant_id, body.kind, body.value, body.service, body.service_owner,
                                    body.provider, body.mitigation_policy, body.capacity_assumptions,
                                    body.exception_note, body.public))
        row = cur.fetchone()
        if _uncovered(row):
            notify(cur, p.tenant_id, "ddos.uncovered_asset", f"Public asset without DDoS coverage: {body.value}",
                   {"asset_id": str(row["id"]), "service": body.service})
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="asset.upsert", target=str(row["id"]),
                     detail=body.model_dump())
    return {"id": str(row["id"]), "covered": not _uncovered(row)}


@router.get("/ddos/coverage")
def ddos_coverage(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.protected_assets WHERE public")
        rows = cur.fetchall()
    covered = [r for r in rows if not _uncovered(r)]
    excepted = [r for r in rows if r["exception_note"]]
    return {"public_endpoints": len(rows), "accounted_for": len(covered),
            "accounted_pct": round(100 * len(covered) / len(rows), 2) if rows else None,
            "with_exceptions": len(excepted),
            "uncovered": [{"id": str(r["id"]), "value": r["value"], "service": r["service"]} for r in rows
                          if _uncovered(r)],
            "missing_fields": [{"id": str(r["id"]), "value": r["value"], "missing": [
                f for f in ("service_owner", "provider", "mitigation_policy", "capacity_assumptions") if not r[f]]}
                for r in rows if any(not r[f] for f in ("service_owner", "provider", "mitigation_policy",
                                                        "capacity_assumptions"))]}


@router.get("/ddos/status")
def ddos_status(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT value, service, mitigation_active FROM aav.protected_assets WHERE mitigation_active")
        mitigating = cur.fetchall()
        cur.execute("SELECT id, signal_kind, category, severity, asset, confirmed, observed_at, received_at, notified_at, "
                    "data->>'simulation' AS simulation FROM aav.external_alerts WHERE signal_kind IN "
                    "('ddos','cdn','load_balancer','waf','api_gateway','dns') AND received_at > now() - interval '24 hours' "
                    "ORDER BY received_at DESC LIMIT 200")
        recent = cur.fetchall()
    return {"mitigation_active": mitigating, "affected_assets": sorted({r["asset"] for r in recent if r["asset"]}),
            "recent_alerts": recent}


@router.get("/service-objectives")
def slos(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.service_objectives ORDER BY service")
        return cur.fetchall()


@router.post("/service-objectives", status_code=201)
def upsert_slo(body: SloIn, p: Principal = Depends(need("assets.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.service_objectives (tenant_id, service, availability_pct, latency_p95_ms, "
                    "success_rate_pct) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, service) DO UPDATE SET "
                    "availability_pct = EXCLUDED.availability_pct, latency_p95_ms = EXCLUDED.latency_p95_ms, "
                    "success_rate_pct = EXCLUDED.success_rate_pct RETURNING id",
                    (p.tenant_id, body.service, body.availability_pct, body.latency_p95_ms, body.success_rate_pct))
        sid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="slo.upsert", target=str(sid),
                     detail=body.model_dump())
    return {"id": str(sid)}


@router.get("/traffic-policies")
def traffic_policies(p: Principal = Depends(need("assets.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.traffic_policies ORDER BY updated_at DESC")
        return cur.fetchall()


@router.post("/traffic-policies", status_code=201)
def propose_traffic_policy(body: TrafficIn, p: Principal = Depends(need("traffic.propose"))):
    if body.control not in ("rate_limit", "bot_control", "challenge", "cache", "geo_block", "ip_block"):
        raise HTTPException(422, "unknown control")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.traffic_policies (tenant_id, service, control, config, customer_impacting, standing) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (p.tenant_id, body.service, body.control,
                                                               json.dumps(body.config), body.customer_impacting,
                                                               body.standing))
        tpid = cur.fetchone()["id"]
        res = propose(cur, tenant_id=p.tenant_id, body=ProposeIn(action_type="apply_traffic_policy",
                                                                 targets=[str(tpid)], reason=body.reason),
                      proposed_by=p.actor, proposer_roles=p.roles, approver_id=p.user_id)
        cur.execute("UPDATE aav.traffic_policies SET action_request_id = %s WHERE id = %s", (res["id"], tpid))
    return {"traffic_policy_id": str(tpid), "action": res}


@router.post("/traffic-policies/{tpid}/rollback", status_code=201)
def rollback_traffic_policy(tpid: UUID, p: Principal = Depends(need("traffic.propose"))):
    with db.tenant_tx(p.tenant_id) as cur:
        res = propose(cur, tenant_id=p.tenant_id, body=ProposeIn(action_type="rollback_traffic_policy",
                                                                 targets=[str(tpid)], reason="rollback"),
                      proposed_by=p.actor, proposer_roles=p.roles, approver_id=p.user_id)
    return res


def execute_traffic_action(cur, tenant_id, action: str, tpid: UUID, request_id) -> dict:
    cur.execute("SELECT * FROM aav.traffic_policies WHERE id = %s FOR UPDATE", (tpid,))
    tp = cur.fetchone()
    if not tp:
        return {"target": str(tpid), "status": "failed", "reason": "not found"}
    kinds = ("ddos", "cdn", "waf", "api_gateway", "load_balancer", "firewall")
    cur.execute("SELECT * FROM aav.integrations WHERE signal_kind = ANY(%s) AND maturity = 'verified_live' AND enabled "
                "ORDER BY array_position(%s, signal_kind)", (list(kinds), list(kinds)))
    integ = None
    for r in cur.fetchall():
        if VERIFIED_ADAPTERS.get((r["signal_kind"], r["config"].get("provider", ""))):
            integ = r
            break
    if integ is None:
        new = "approved" if action == "apply_traffic_policy" else tp["status"]
        cur.execute("UPDATE aav.traffic_policies SET status = %s, updated_at = now() WHERE id = %s", (new, tpid))
        return {"target": str(tpid), "status": "failed",
                "reason": "no verified_live provider adapter; policy approved but not applied"}
    from app import providers
    from app.routers.integrations import build_adapter
    try:
        adapter = build_adapter(cur, integ)
        result = adapter.apply(tp) if action == "apply_traffic_policy" else adapter.rollback(tp)
    except providers.ProviderError as exc:
        new = "approved" if action == "apply_traffic_policy" else tp["status"]
        cur.execute("UPDATE aav.traffic_policies SET status = %s, updated_at = now() WHERE id = %s", (new, tpid))
        return {"target": str(tpid), "status": "failed", "reason": str(exc)}
    final = "active" if action == "apply_traffic_policy" else "rolled_back"
    cur.execute("UPDATE aav.traffic_policies SET status = %s, config = config || %s, updated_at = now() WHERE id = %s",
                (final, json.dumps({"provider_ref": result} if action == "apply_traffic_policy" else
                                   {"provider_rollback": result}), tpid))
    return {"target": str(tpid), "status": final, "provider_result": result}


@router.get("/coverage")
def coverage(p: Principal = Depends(need("coverage.read"))):
    """THR-00 / DLV-23: supported assets, available signals and gaps per protection layer."""
    from app.routers.integrations import INGEST_CATEGORIES
    layers = {
        "endpoint": ["windows", "macos", "linux"],
        "identity": ["identity"], "phishing": ["email", "url_reputation"], "web_api": ["waf", "api_gateway"],
        "network": ["dns", "firewall"], "cloud": ["cloud_audit"], "supply_chain": ["vulnerability"],
        "insider": ["dlp"], "physical": ["physical"], "ddos": ["ddos", "cdn", "load_balancer", "dns"],
        "recovery": ["backup"],
    }
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT os, count(*) AS n FROM aav.devices WHERE retired_at IS NULL GROUP BY os")
        oses = {r["os"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT signal_kind, maturity FROM aav.integrations WHERE enabled")
        signals: dict = {}
        for r in cur.fetchall():
            signals.setdefault(r["signal_kind"], set()).add(r["maturity"])
        out = []
        for layer, kinds in layers.items():
            if layer == "endpoint":
                assets = [{"os": k, "devices": v} for k, v in oses.items()]
                avail = sorted(oses)
                gaps = [f"no enrolled {k} devices" for k in kinds if k not in oses]
            else:
                assets = []
                avail = sorted(f"{k}({','.join(sorted(signals[k]))})" for k in kinds if k in signals)
                gaps = [f"no enabled {k} integration" for k in kinds if k not in signals] + \
                       [f"{k} integration is test_only (simulation)" for k in kinds
                        if k in signals and "verified_live" not in signals[k]]
            cur.execute("INSERT INTO aav.coverage_records (tenant_id, layer, supported_assets, available_signals, gaps) "
                        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id, layer) DO UPDATE SET supported_assets = "
                        "EXCLUDED.supported_assets, available_signals = EXCLUDED.available_signals, gaps = EXCLUDED.gaps, "
                        "updated_at = now()", (p.tenant_id, layer, json.dumps(assets), json.dumps(avail), json.dumps(gaps)))
            out.append({"layer": layer, "supported_assets": assets, "available_signals": avail, "gaps": gaps})
        _ = INGEST_CATEGORIES
    return out
