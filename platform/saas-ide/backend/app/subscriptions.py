"""Subscriptions: 30-day trial (100% ads) -> £4.99/month (5% of ads) -> free tier (100% ads).

The server is the only authority on a user's plan and ad rate. Purchases are accepted only after
verification with the provider:
  * Stripe (web + desktop): HMAC-signed webhooks; checkout binds the user's opaque account_id.
  * Google Play (Android): Play Developer API subscriptionsv2; obfuscatedExternalAccountId must
    equal the caller's account_id; purchases are acknowledged.
  * App Store (iOS): App Store Server API; transaction JWS verified against the x5c chain and a
    pinned Apple root; appAccountToken must equal the caller's account_id.
The £4.99 price itself is configured in the Stripe / Play Console / App Store Connect products.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

TRIAL_DAYS = 30
FULL_AD_RATE = 1.0
SUBSCRIBER_AD_RATE = 0.05  # "95% ads off"
SUBSCRIBED_STATUSES = ("active", "grace", "canceled")  # canceled = no renewal, paid until period end
PRICE_LABEL = os.getenv("IDE_SUBSCRIPTION_PRICE_LABEL", "£4.99/month")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class BillingError(Exception):
    status_code = 400


class BillingDenied(BillingError):
    status_code = 403


class BillingUnavailable(BillingError):
    status_code = 503


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return _utc(dt).isoformat() if dt else None


# --------------------------------------------------------------------------- entitlement policy
def entitlement_state(trial_started_at: datetime, status: str, period_end: datetime | None,
                      now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    trial_started_at = _utc(trial_started_at)
    period_end = _utc(period_end)
    trial_ends = trial_started_at + timedelta(days=TRIAL_DAYS)
    subscribed = status in SUBSCRIBED_STATUSES and period_end is not None and period_end > now
    if subscribed:
        plan, rate = "pro", SUBSCRIBER_AD_RATE
    elif now < trial_ends:
        plan, rate = "trial", FULL_AD_RATE
    else:
        plan, rate = "free", FULL_AD_RATE
    days_left = max(0, math.ceil((trial_ends - now).total_seconds() / 86400)) if plan == "trial" else 0
    return {"plan": plan, "ad_rate": rate, "subscribed": subscribed,
            "trial_ends_at": _iso(trial_ends), "trial_days_left": days_left,
            "renews_at": _iso(period_end) if subscribed else None,
            "will_renew": subscribed and status != "canceled", "price": PRICE_LABEL}


# --------------------------------------------------------------------------- persistence
def ensure_entitlement(db: Session, subject: str) -> dict:
    """Create the caller's row on first sight (this starts the 30-day trial) and return it."""
    db.execute(text("""INSERT INTO ide_entitlements(subject, account_id)
                       VALUES (:s, :a) ON CONFLICT (subject) DO NOTHING"""),
               {"s": subject, "a": str(uuid.uuid4())})
    row = db.execute(text("""SELECT account_id, trial_started_at, status, current_period_end,
                                    source, customer_ref
                             FROM ide_entitlements WHERE subject=:s"""), {"s": subject}).one()
    db.commit()
    return {"account_id": str(row[0]), "trial_started_at": row[1], "status": row[2],
            "current_period_end": row[3], "source": row[4], "customer_ref": row[5]}


def record_event(db: Session, provider: str, event_id: str) -> bool:
    """True the first time a provider event is seen; False for replays (idempotency)."""
    inserted = db.execute(text("""INSERT INTO ide_billing_events(provider, event_id)
                                  VALUES (:p, :e) ON CONFLICT DO NOTHING RETURNING 1"""),
                          {"p": provider, "e": event_id[:255]}).first()
    return inserted is not None


def apply_update(db: Session, update: dict) -> bool:
    """Apply a verified provider state; older events never overwrite newer ones."""
    result = db.execute(text("""UPDATE ide_entitlements SET
              source=:source, status=:status, current_period_end=:period_end,
              external_ref=:external_ref,
              customer_ref=COALESCE(:customer_ref, customer_ref),
              last_event_at=:event_time, updated_at=now()
            WHERE account_id=CAST(:account_id AS uuid)
              AND (last_event_at IS NULL OR last_event_at <= :event_time)"""),
        {"source": update["source"], "status": update["status"], "period_end": update["period_end"],
         "external_ref": update["external_ref"], "customer_ref": update.get("customer_ref"),
         "event_time": update["event_time"], "account_id": update["account_id"]})
    return result.rowcount == 1


def _require_account(value) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise BillingDenied("purchase is not bound to an AEP-X account")
    return value


# --------------------------------------------------------------------------- Stripe
_STRIPE_STATUS = {"active": "active", "trialing": "active", "past_due": "grace",
                  "canceled": "canceled", "unpaid": "expired", "incomplete_expired": "expired",
                  "paused": "expired", "incomplete": "none"}


def verify_stripe_signature(payload: bytes, header: str | None, secret: str | None,
                            now: float | None = None, tolerance: int = 300) -> dict:
    if not secret or len(secret) < 16:
        raise BillingUnavailable("Stripe webhook secret not configured")
    if not header or len(header) > 2048:
        raise BillingDenied("missing Stripe signature")
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    timestamps = [v for k, v in parts if k == "t"]
    signatures = [v for k, v in parts if k == "v1"]
    if len(timestamps) != 1 or not timestamps[0].isdigit() or not signatures:
        raise BillingDenied("malformed Stripe signature")
    ts = int(timestamps[0])
    if abs((now if now is not None else time.time()) - ts) > tolerance:
        raise BillingDenied("stale Stripe signature")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise BillingDenied("invalid Stripe signature")
    event = json.loads(payload)
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise BillingDenied("malformed Stripe event")
    return event


def stripe_subscription_update(event: dict) -> dict | None:
    kind = event.get("type")
    if kind not in ("customer.subscription.created", "customer.subscription.updated",
                    "customer.subscription.deleted"):
        return None
    sub = event["data"]["object"]
    account = _require_account((sub.get("metadata") or {}).get("aepx_account"))
    period_end = sub.get("current_period_end")
    if period_end is None:  # newer Stripe API versions report it per subscription item
        items = (sub.get("items") or {}).get("data") or []
        period_end = max((i.get("current_period_end") or 0 for i in items), default=None) or None
    status = "canceled" if kind.endswith(".deleted") else _STRIPE_STATUS.get(sub.get("status"), "none")
    return {"account_id": account, "source": "stripe", "status": status,
            "period_end": datetime.fromtimestamp(period_end, timezone.utc) if period_end else None,
            "external_ref": str(sub["id"])[:255], "customer_ref": str(sub.get("customer") or "")[:255] or None,
            "event_time": datetime.fromtimestamp(int(event["created"]), timezone.utc)}


def _stripe_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
        raise BillingUnavailable("Stripe is not configured")
    return key


def _public_url() -> str:
    url = os.getenv("IDE_PUBLIC_URL", "").rstrip("/")
    if not url.startswith("https://"):
        raise BillingUnavailable("IDE_PUBLIC_URL (https) is required for billing redirects")
    return url


def create_stripe_checkout(account_id: str, http=httpx) -> str:
    price = os.getenv("STRIPE_PRICE_ID", "")
    if not price.startswith("price_"):
        raise BillingUnavailable("STRIPE_PRICE_ID is not configured")
    public = _public_url()
    response = http.post("https://api.stripe.com/v1/checkout/sessions", auth=(_stripe_key(), ""), timeout=15,
                         headers={"Idempotency-Key": f"checkout-{account_id}-{int(time.time() // 600)}"},
                         data={"mode": "subscription", "line_items[0][price]": price,
                               "line_items[0][quantity]": "1",
                               "success_url": f"{public}/?billing=success", "cancel_url": f"{public}/?billing=cancel",
                               "client_reference_id": account_id,
                               "metadata[aepx_account]": account_id,
                               "subscription_data[metadata][aepx_account]": account_id})
    if response.status_code != 200:
        raise BillingUnavailable("Stripe checkout unavailable")
    url = response.json().get("url", "")
    if not url.startswith("https://checkout.stripe.com/"):
        raise BillingUnavailable("unexpected Stripe checkout URL")
    return url


def create_stripe_portal(customer_ref: str | None, http=httpx) -> str:
    if not customer_ref or not customer_ref.startswith("cus_"):
        raise BillingDenied("no Stripe subscription for this account")
    response = http.post("https://api.stripe.com/v1/billing_portal/sessions", auth=(_stripe_key(), ""), timeout=15,
                         data={"customer": customer_ref, "return_url": _public_url() + "/"})
    if response.status_code != 200:
        raise BillingUnavailable("Stripe billing portal unavailable")
    url = response.json().get("url", "")
    if not url.startswith("https://billing.stripe.com/"):
        raise BillingUnavailable("unexpected Stripe portal URL")
    return url


# --------------------------------------------------------------------------- Google Play
_PLAY_STATE = {"SUBSCRIPTION_STATE_ACTIVE": "active", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "grace",
               "SUBSCRIPTION_STATE_CANCELED": "canceled", "SUBSCRIPTION_STATE_ON_HOLD": "expired",
               "SUBSCRIPTION_STATE_PAUSED": "expired", "SUBSCRIPTION_STATE_EXPIRED": "expired"}
_PLAY_TOKEN_RE = re.compile(r"^[A-Za-z0-9._\-]{10,1024}$")


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _google_access_token(http) -> str:
    path = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE", "")
    if not path or not os.path.isfile(path):
        raise BillingUnavailable("Google Play service account not configured")
    with open(path, encoding="utf-8") as handle:
        account = json.load(handle)
    now = int(time.time())
    assertion = jwt.encode({"iss": account["client_email"], "aud": account["token_uri"], "iat": now, "exp": now + 600,
                            "scope": "https://www.googleapis.com/auth/androidpublisher"},
                           account["private_key"], algorithm="RS256")
    response = http.post(account["token_uri"], timeout=15,
                         data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if response.status_code != 200:
        raise BillingUnavailable("Google authorization failed")
    return response.json()["access_token"]


def play_subscription_update(account_id: str, data: dict, product_id: str) -> dict:
    owner = ((data.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId"))
    if owner != account_id:
        raise BillingDenied("purchase belongs to a different account")
    items = [i for i in data.get("lineItems") or [] if i.get("productId") == product_id]
    if not items:
        raise BillingDenied("purchase is not the AEP-X subscription")
    expiry = max(_parse_rfc3339(i["expiryTime"]) for i in items if i.get("expiryTime"))
    order = str(data.get("latestOrderId") or "").split("..")[0]
    return {"account_id": account_id, "source": "google_play",
            "status": _PLAY_STATE.get(data.get("subscriptionState"), "none"), "period_end": expiry,
            "external_ref": (order or "play-unknown")[:255], "event_time": datetime.now(timezone.utc)}


def verify_google_play(account_id: str, purchase_token: str, http=httpx) -> dict:
    package = os.getenv("GOOGLE_PLAY_PACKAGE", "")
    product = os.getenv("GOOGLE_PLAY_PRODUCT_ID", "")
    if not package or not product:
        raise BillingUnavailable("Google Play product not configured")
    if not isinstance(purchase_token, str) or not _PLAY_TOKEN_RE.fullmatch(purchase_token):
        raise BillingDenied("invalid purchase token")
    bearer = {"Authorization": "Bearer " + _google_access_token(http)}
    base = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package}/purchases"
    response = http.get(f"{base}/subscriptionsv2/tokens/{purchase_token}", headers=bearer, timeout=15)
    if response.status_code == 404:
        raise BillingDenied("unknown purchase")
    if response.status_code != 200:
        raise BillingUnavailable("Google Play verification unavailable")
    data = response.json()
    update = play_subscription_update(account_id, data, product)
    if data.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING" and update["status"] in ("active", "grace"):
        ack = http.post(f"{base}/subscriptions/{product}/tokens/{purchase_token}:acknowledge", headers=bearer,
                        json={}, timeout=15)
        if ack.status_code not in (200, 204):
            raise BillingUnavailable("Google Play acknowledgement failed")
    return update


# --------------------------------------------------------------------------- App Store
_APPLE_STATUS = {1: "active", 2: "expired", 3: "expired", 4: "grace", 5: "revoked"}


def verify_apple_jws(token: str, root_sha256: str, now: datetime | None = None) -> dict:
    """Verify a StoreKit JWS: x5c chain -> pinned Apple root, then ES256 signature."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    pinned = (root_sha256 or "").replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", pinned):
        raise BillingUnavailable("APPLE_ROOT_CA_SHA256 is not configured")
    header = jwt.get_unverified_header(token)
    chain = header.get("x5c") or []
    if header.get("alg") != "ES256" or len(chain) < 2:
        raise BillingDenied("invalid App Store signature header")
    certs = [x509.load_der_x509_certificate(base64.b64decode(c)) for c in chain]
    now = now or datetime.now(timezone.utc)
    for cert in certs:
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise BillingDenied("App Store certificate outside validity window")
    for child, parent in zip(certs, certs[1:]):
        child.verify_directly_issued_by(parent)
    if certs[-1].fingerprint(hashes.SHA256()).hex() != pinned:
        raise BillingDenied("App Store chain does not end at the pinned Apple root")
    return jwt.decode(token, certs[0].public_key(), algorithms=["ES256"], options={"verify_aud": False})


def apple_apps() -> dict[str, str]:
    """Configured iOS apps as {bundle_id: product_id}.

    APPLE_BUNDLE_ID and APPLE_PRODUCT_ID are comma-separated lists paired by position, so the native
    companion and the IDE wrapper (two App Store apps, each with its own subscription product) can both sell
    the plan. A single value in each keeps the original one-app behaviour.
    """
    bundles = [b.strip() for b in os.getenv("APPLE_BUNDLE_ID", "").split(",") if b.strip()]
    products = [p.strip() for p in os.getenv("APPLE_PRODUCT_ID", "").split(",") if p.strip()]
    if not bundles or len(bundles) != len(products):
        raise BillingUnavailable("App Store product not configured")
    return dict(zip(bundles, products))


def _apple_api_token(bundle: str) -> str:
    issuer, key_id = os.getenv("APPLE_ISSUER_ID", ""), os.getenv("APPLE_KEY_ID", "")
    key_path = os.getenv("APPLE_PRIVATE_KEY_FILE", "")
    if not (issuer and key_id and bundle and key_path and os.path.isfile(key_path)):
        raise BillingUnavailable("App Store Server API not configured")
    with open(key_path, encoding="utf-8") as handle:
        key = handle.read()
    now = int(time.time())
    return jwt.encode({"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1", "bid": bundle},
                      key, algorithm="ES256", headers={"kid": key_id, "typ": "JWT"})


def app_store_update(account_id: str, payload: dict, root_sha256: str, bundle: str, product: str) -> dict:
    best = None
    for group in payload.get("data") or []:
        for last in group.get("lastTransactions") or []:
            tx = verify_apple_jws(last["signedTransactionInfo"], root_sha256)
            if tx.get("bundleId") != bundle or tx.get("productId") != product:
                continue
            if str(tx.get("appAccountToken", "")).lower() != account_id:
                raise BillingDenied("purchase belongs to a different account")
            candidate = {"account_id": account_id, "source": "app_store",
                         "status": _APPLE_STATUS.get(last.get("status"), "none"),
                         "period_end": datetime.fromtimestamp(int(tx["expiresDate"]) / 1000, timezone.utc),
                         "external_ref": str(tx["originalTransactionId"])[:255],
                         "event_time": datetime.now(timezone.utc)}
            if best is None or candidate["period_end"] > best["period_end"]:
                best = candidate
    if best is None:
        raise BillingDenied("no AEP-X subscription in this transaction history")
    return best


def verify_app_store(account_id: str, original_transaction_id: str, http=httpx,
                     bundle_id: str | None = None) -> dict:
    if not isinstance(original_transaction_id, str) or not re.fullmatch(r"\d{1,32}", original_transaction_id):
        raise BillingDenied("invalid original transaction id")
    apps = apple_apps()
    bundle = bundle_id or next(iter(apps))
    if bundle not in apps:
        raise BillingDenied("unknown iOS app")
    product = apps[bundle]
    host = ("https://api.storekit-sandbox.itunes.apple.com" if os.getenv("APPLE_ENVIRONMENT") == "sandbox"
            else "https://api.storekit.itunes.apple.com")
    response = http.get(f"{host}/inApps/v1/subscriptions/{original_transaction_id}", timeout=15,
                        headers={"Authorization": "Bearer " + _apple_api_token(bundle)})
    if response.status_code == 404:
        raise BillingDenied("unknown App Store transaction")
    if response.status_code != 200:
        raise BillingUnavailable("App Store verification unavailable")
    return app_store_update(account_id, response.json(), os.getenv("APPLE_ROOT_CA_SHA256", ""), bundle, product)
