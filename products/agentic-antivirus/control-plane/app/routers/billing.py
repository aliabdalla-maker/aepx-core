"""Licence, trial, ads configuration and store-receipt verification endpoints.

Licences are only created from a provider-verified purchase (no manual "mark paid").
Google Play: Android Publisher API purchases.subscriptionsv2.get with a service account
(AAV_PLAY_SERVICE_ACCOUNT_FILE). App Store and web checkout verification are not configured
in this release (register B-03 / open decision on web payment provider) and return 503.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app import audit, crypto, db, licensing, rbac
from app.config import settings
from app.deps import Principal, need, tenant_principal

router = APIRouter(prefix="/v1", tags=["billing"])

_play_transport: httpx.BaseTransport | None = None


def set_play_transport(t):
    global _play_transport
    _play_transport = t


class LicenceSettingsIn(BaseModel):
    licence_unit: str
    post_trial_policy: str
    acknowledge_lock_all_disables_protection: bool = False


class PlayReceiptIn(BaseModel):
    purchase_token: str = Field(min_length=10, max_length=4096)
    holder_kind: str
    holder_id: UUID


@router.get("/licence")
def licence(p: Principal = Depends(tenant_principal), device_id: UUID | None = None):
    with db.tenant_tx(p.tenant_id) as cur:
        return licensing.entitlement(cur, tenant_id=p.tenant_id, user_id=p.user_id, device_id=device_id)


@router.get("/agent/licence")
def agent_licence(x_device_key: str | None = Header(default=None)):
    from app.routers.agent import _device
    d = _device(x_device_key)
    with db.tenant_tx(d["tenant_id"]) as cur:
        ent = licensing.entitlement(cur, tenant_id=d["tenant_id"], device_id=d["device_id"])
    bundle = {"device_id": str(d["device_id"]), "entitlement": ent, "issued_at": datetime.now(timezone.utc).isoformat()}
    return {"bundle": bundle, "signature": crypto.sign(bundle)}


@router.put("/licence/settings")
def licence_settings(body: LicenceSettingsIn, p: Principal = Depends(need("billing.manage"))):
    if body.licence_unit not in ("per_user", "per_device"):
        raise HTTPException(422, "licence_unit must be per_user or per_device")
    if body.post_trial_policy not in ("paywall_console_keep_protection", "free_with_full_ads", "lock_all"):
        raise HTTPException(422, "unknown post_trial_policy")
    if body.post_trial_policy == "lock_all" and not body.acknowledge_lock_all_disables_protection:
        raise HTTPException(409, "lock_all stops endpoint protection after the trial; set "
                                 "acknowledge_lock_all_disables_protection=true to confirm")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.subscriptions SET licence_unit = %s, post_trial_policy = %s, updated_at = now() "
                    "WHERE tenant_id = %s", (body.licence_unit, body.post_trial_policy, p.tenant_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="billing.settings", detail=body.model_dump())
    return {"updated": True}


@router.get("/ads/config")
def public_ads_config():
    """Ad identifiers and placement rules for clients (no secrets)."""
    cfg = licensing.ads_config()
    return {k: cfg[k] for k in ("publisher_id", "adsense", "admob", "ad_rate", "placements")}


def _play_access_token(sa: dict) -> str:
    now = int(time.time())
    assertion = jwt.encode({"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/androidpublisher",
                            "aud": sa["token_uri"], "iat": now, "exp": now + 600}, sa["private_key"], algorithm="RS256")
    with httpx.Client(timeout=10, transport=_play_transport) as c:
        r = c.post(sa["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                          "assertion": assertion})
    r.raise_for_status()
    return r.json()["access_token"]


@router.post("/billing/google-play/verify", status_code=201)
def verify_play(body: PlayReceiptIn, p: Principal = Depends(tenant_principal)):
    sa_file = os.getenv("AAV_PLAY_SERVICE_ACCOUNT_FILE", "")
    if not sa_file:
        raise HTTPException(503, "Google Play verification not configured")
    if body.holder_kind not in ("user", "device"):
        raise HTTPException(422, "holder_kind must be user or device")
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT licence_unit FROM aav.subscriptions WHERE tenant_id = %s", (p.tenant_id,))
        unit = cur.fetchone()["licence_unit"]
        if (unit == "per_user") != (body.holder_kind == "user"):
            raise HTTPException(409, f"tenant licenses {unit}; holder_kind mismatch")
        if body.holder_kind == "user" and body.holder_id != p.user_id and not rbac.allowed(p.roles, "billing.manage"):
            raise HTTPException(403, "can only license yourself")
        if body.holder_kind == "device":
            cur.execute("SELECT 1 FROM aav.devices WHERE id = %s", (body.holder_id,))
            if not cur.fetchone():
                raise HTTPException(404, "device not found")
    with open(sa_file, encoding="utf-8") as fh:
        sa = json.load(fh)
    try:
        token = _play_access_token(sa)
        url = (f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
               f"{settings.play_package_name}/purchases/subscriptionsv2/tokens/{body.purchase_token}")
        with httpx.Client(timeout=10, transport=_play_transport) as c:
            r = c.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        sub = r.json()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, f"Play verification failed: {type(exc).__name__}")
    if sub.get("subscriptionState") not in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"):
        raise HTTPException(402, f"subscription not active ({sub.get('subscriptionState')})")
    item = (sub.get("lineItems") or [{}])[0]
    if item.get("productId") != licensing.ads_config()["pricing"]["store_product_id"]:
        raise HTTPException(409, "unexpected product")
    start = datetime.fromisoformat(sub["startTime"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(item["expiryTime"].replace("Z", "+00:00"))
    price = (item.get("autoRenewingPlan") or {}).get("recurringPrice") or {}
    amount_minor = int(price.get("units", "0")) * 100 + int(price.get("nanos", 0)) // 10_000_000
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.licences (tenant_id, holder_kind, holder_id, provider, provider_ref, period_start, "
                    "period_end, amount_minor, currency) VALUES (%s,%s,%s,'google_play',%s,%s,%s,%s,%s) "
                    "ON CONFLICT (provider, provider_ref) DO UPDATE SET period_end = EXCLUDED.period_end, status = 'active' "
                    "RETURNING id", (p.tenant_id, body.holder_kind, body.holder_id,
                                     sub.get("latestOrderId") or crypto.token_hash(body.purchase_token), start, end,
                                     amount_minor, price.get("currencyCode", "GBP")))
        lid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="billing.licence_verified", target=str(lid),
                     detail={"provider": "google_play", "holder": f"{body.holder_kind}:{body.holder_id}",
                             "period_end": end.isoformat()})
    return {"licence_id": str(lid), "period_end": end.isoformat()}


@router.post("/billing/app-store/verify")
def verify_app_store(p: Principal = Depends(tenant_principal)):
    raise HTTPException(503, "App Store verification not configured (needs Apple developer account and keys)")


@router.post("/billing/web/checkout")
def web_checkout(p: Principal = Depends(tenant_principal)):
    raise HTTPException(503, "web payment provider not selected")
