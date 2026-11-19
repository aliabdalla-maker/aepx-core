"""Subscription policy and provider verification: pure tests, no network or database."""
import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app import subscriptions as subs

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
ACCOUNT = str(uuid.uuid4())


# ------------------------------------------------------------------ plan / ad-rate policy
def test_new_user_is_on_30_day_trial_with_full_ads():
    s = subs.entitlement_state(NOW, "none", None, now=NOW)
    assert (s["plan"], s["ad_rate"], s["trial_days_left"], s["subscribed"]) == ("trial", 1.0, 30, False)
    assert s["price"] == "£4.99/month"


def test_trial_expires_into_free_tier_with_full_ads():
    s = subs.entitlement_state(NOW - timedelta(days=30, seconds=1), "none", None, now=NOW)
    assert (s["plan"], s["ad_rate"], s["trial_days_left"]) == ("free", 1.0, 0)


def test_subscriber_sees_5_percent_of_ads_even_during_trial():
    s = subs.entitlement_state(NOW, "active", NOW + timedelta(days=30), now=NOW)
    assert (s["plan"], s["ad_rate"], s["will_renew"]) == ("pro", 0.05, True)


def test_canceled_keeps_benefit_until_period_end_then_free():
    paid = subs.entitlement_state(NOW - timedelta(days=60), "canceled", NOW + timedelta(days=3), now=NOW)
    assert (paid["plan"], paid["will_renew"]) == ("pro", False)
    lapsed = subs.entitlement_state(NOW - timedelta(days=60), "canceled", NOW - timedelta(seconds=1), now=NOW)
    assert lapsed["plan"] == "free"


@pytest.mark.parametrize("status", ["expired", "revoked", "none"])
def test_inactive_statuses_never_grant_pro(status):
    assert subs.entitlement_state(NOW - timedelta(days=60), status, NOW + timedelta(days=10), now=NOW)["plan"] == "free"


# ------------------------------------------------------------------ Stripe webhooks
SECRET = "whsec_test_0123456789abcdef"


def _signed(event: dict, ts: int, secret: str = SECRET):
    payload = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, f"t={ts},v1={sig}"


def _sub_event(kind="customer.subscription.updated", status="active", account=ACCOUNT, created=1_700_000_000):
    return {"id": "evt_1", "type": kind, "created": created,
            "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": status,
                                "metadata": {"aepx_account": account},
                                "items": {"data": [{"current_period_end": created + 30 * 86400}]}}}}


def test_stripe_signature_accepts_valid_and_rejects_tampering():
    payload, header = _signed(_sub_event(), 1_700_000_000)
    assert subs.verify_stripe_signature(payload, header, SECRET, now=1_700_000_010)["id"] == "evt_1"
    with pytest.raises(subs.BillingDenied):
        subs.verify_stripe_signature(payload.replace(b"active", b"canceled"), header, SECRET, now=1_700_000_010)
    with pytest.raises(subs.BillingDenied):
        subs.verify_stripe_signature(payload, header, SECRET, now=1_700_000_000 + 301)  # replay window
    with pytest.raises(subs.BillingDenied):
        subs.verify_stripe_signature(payload, _signed(_sub_event(), 1_700_000_000, "whsec_other_secret_value")[1],
                                     SECRET, now=1_700_000_010)
    with pytest.raises(subs.BillingUnavailable):
        subs.verify_stripe_signature(payload, header, "", now=1_700_000_010)


def test_stripe_event_mapping():
    u = subs.stripe_subscription_update(_sub_event(status="past_due"))
    assert (u["account_id"], u["status"], u["source"], u["customer_ref"]) == (ACCOUNT, "grace", "stripe", "cus_1")
    assert u["period_end"] == datetime.fromtimestamp(1_700_000_000 + 30 * 86400, timezone.utc)
    assert subs.stripe_subscription_update(_sub_event(kind="customer.subscription.deleted"))["status"] == "canceled"
    assert subs.stripe_subscription_update({"type": "invoice.paid"}) is None
    with pytest.raises(subs.BillingDenied):
        subs.stripe_subscription_update(_sub_event(account="not-a-uuid"))


class FakeHttp:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def _next(self, method, url, **kw):
        self.calls.append((method, url, kw))
        status, body = self.responses.pop(0)
        return type("R", (), {"status_code": status, "json": lambda self_: body})()

    def post(self, url, **kw):
        return self._next("POST", url, **kw)

    def get(self, url, **kw):
        return self._next("GET", url, **kw)


def test_stripe_checkout_binds_account_and_validates_url(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_499gbp")
    monkeypatch.setenv("IDE_PUBLIC_URL", "https://ide.softwareequality.com")
    http = FakeHttp([(200, {"url": "https://checkout.stripe.com/c/pay/cs_test"})])
    assert subs.create_stripe_checkout(ACCOUNT, http=http).startswith("https://checkout.stripe.com/")
    data = http.calls[0][2]["data"]
    assert data["subscription_data[metadata][aepx_account]"] == ACCOUNT and data["mode"] == "subscription"
    with pytest.raises(subs.BillingUnavailable):
        subs.create_stripe_checkout(ACCOUNT, http=FakeHttp([(200, {"url": "https://evil.example/pay"})]))
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    with pytest.raises(subs.BillingUnavailable):
        subs.create_stripe_checkout(ACCOUNT, http=FakeHttp([]))


# ------------------------------------------------------------------ Google Play
def _play(owner=ACCOUNT, product="aepx_pro_monthly", state="SUBSCRIPTION_STATE_ACTIVE"):
    return {"subscriptionState": state, "latestOrderId": "GPA.1111-2222-3333-44444..3",
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": owner},
            "lineItems": [{"productId": product, "expiryTime": "2026-12-15T12:00:00Z"}]}


def test_play_mapping_requires_same_account_and_product():
    u = subs.play_subscription_update(ACCOUNT, _play(), "aepx_pro_monthly")
    assert (u["status"], u["external_ref"]) == ("active", "GPA.1111-2222-3333-44444")
    assert u["period_end"] == datetime(2026, 12, 15, 12, tzinfo=timezone.utc)
    assert subs.play_subscription_update(ACCOUNT, _play(state="SUBSCRIPTION_STATE_IN_GRACE_PERIOD"),
                                         "aepx_pro_monthly")["status"] == "grace"
    with pytest.raises(subs.BillingDenied):
        subs.play_subscription_update(ACCOUNT, _play(owner=str(uuid.uuid4())), "aepx_pro_monthly")
    with pytest.raises(subs.BillingDenied):
        subs.play_subscription_update(ACCOUNT, _play(product="other"), "aepx_pro_monthly")


def test_play_verify_rejects_bad_token_before_any_network(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLAY_PACKAGE", "com.equalitysoftware.aepx.companion")
    monkeypatch.setenv("GOOGLE_PLAY_PRODUCT_ID", "aepx_pro_monthly")
    http = FakeHttp([])
    with pytest.raises(subs.BillingDenied):
        subs.verify_google_play(ACCOUNT, "../../etc/passwd", http=http)
    assert http.calls == []


# ------------------------------------------------------------------ App Store (real x5c chain)
def _cert(subject, issuer_name, key, signer_key, ca, days=3650):
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(NOW - timedelta(days=1)).not_valid_after(NOW + timedelta(days=days))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    return builder.sign(signer_key, hashes.SHA256())


@pytest.fixture(scope="module")
def apple_chain():
    root_k, mid_k, leaf_k = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert("Test Root", "Test Root", root_k, root_k, True)
    mid = _cert("Test WWDR", "Test Root", mid_k, root_k, True)
    leaf = _cert("Test Leaf", "Test WWDR", leaf_k, mid_k, False)
    x5c = [base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode() for c in (leaf, mid, root)]
    pin = root.fingerprint(hashes.SHA256()).hex()

    def sign(claims):
        return jwt.encode(claims, leaf_k, algorithm="ES256", headers={"x5c": x5c})
    return sign, pin


def _tx(account=ACCOUNT, product="aepx.pro.monthly", bundle="com.equalitysoftware.aepx"):
    return {"bundleId": bundle, "productId": product, "appAccountToken": account,
            "originalTransactionId": "2000000123456789",
            "expiresDate": int((NOW + timedelta(days=30)).timestamp() * 1000)}


def test_apple_jws_chain_and_pin(apple_chain):
    sign, pin = apple_chain
    token = sign(_tx())
    assert subs.verify_apple_jws(token, pin, now=NOW)["productId"] == "aepx.pro.monthly"
    with pytest.raises(subs.BillingDenied):
        subs.verify_apple_jws(token, "00" * 32, now=NOW)  # chain not anchored at the pinned root
    with pytest.raises(subs.BillingUnavailable):
        subs.verify_apple_jws(token, "", now=NOW)  # fail closed without a pin
    forged = jwt.encode(_tx(), ec.generate_private_key(ec.SECP256R1()), algorithm="ES256",
                        headers={"x5c": jwt.get_unverified_header(token)["x5c"]})
    with pytest.raises(jwt.InvalidSignatureError):
        subs.verify_apple_jws(forged, pin, now=NOW)


def test_app_store_update_binds_account_and_product(apple_chain):
    sign, pin = apple_chain
    bundle, product = "com.equalitysoftware.aepx", "aepx.pro.monthly"
    payload = {"data": [{"lastTransactions": [{"status": 1, "signedTransactionInfo": sign(_tx())}]}]}
    u = subs.app_store_update(ACCOUNT, payload, pin, bundle, product)
    assert (u["status"], u["external_ref"], u["source"]) == ("active", "2000000123456789", "app_store")
    stolen = {"data": [{"lastTransactions": [{"status": 1, "signedTransactionInfo": sign(_tx(account=str(uuid.uuid4())))}]}]}
    with pytest.raises(subs.BillingDenied):
        subs.app_store_update(ACCOUNT, stolen, pin, bundle, product)
    other = {"data": [{"lastTransactions": [{"status": 1, "signedTransactionInfo": sign(_tx(product="other"))}]}]}
    with pytest.raises(subs.BillingDenied):
        subs.app_store_update(ACCOUNT, other, pin, bundle, product)


def test_apple_apps_pairs_bundles_with_products(monkeypatch):
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.equalitysoftware.aepx.companion, com.equalitysoftware.aepx.ide")
    monkeypatch.setenv("APPLE_PRODUCT_ID", "com.softwareequality.aepx.pro.monthly,com.softwareequality.aepx.ide.pro.monthly")
    assert subs.apple_apps() == {
        "com.equalitysoftware.aepx.companion": "com.softwareequality.aepx.pro.monthly",
        "com.equalitysoftware.aepx.ide": "com.softwareequality.aepx.ide.pro.monthly",
    }
    monkeypatch.setenv("APPLE_PRODUCT_ID", "only-one")
    with pytest.raises(subs.BillingUnavailable):
        subs.apple_apps()


def test_verify_app_store_rejects_unconfigured_bundle(monkeypatch):
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.equalitysoftware.aepx.companion")
    monkeypatch.setenv("APPLE_PRODUCT_ID", "com.softwareequality.aepx.pro.monthly")
    with pytest.raises(subs.BillingDenied, match="unknown iOS app"):
        subs.verify_app_store("0b6f3c2e-8d1a-4f1e-9a51-2a7c9e4d5b60", "2000000123", bundle_id="com.evil.app")
