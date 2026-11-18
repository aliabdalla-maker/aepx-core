"""Owner requirement 18 Nov 2026: 30-day trial with 100% ads (AdMob/AdSense); GBP 4.99/month per
user or per device; 95% ad reduction after payment; three post-trial policies; all supplied
AdMob identifiers present."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from conftest import PRODUCT


@pytest.fixture
def org(new_account, invite, enrol):
    admin = new_account("bill")
    user = invite(admin, "endpoint_user")
    dev = enrol(admin, "phone-1", "android")
    return admin, user, dev


def _expire_trial(admin_sql, tenant):
    admin_sql("UPDATE aav.subscriptions SET trial_started_at = now() - interval '31 days' WHERE tenant_id = %s", tenant)


def _grant_licence(admin_sql, tenant, kind, holder):
    now = datetime.now(timezone.utc)
    admin_sql("INSERT INTO aav.licences (tenant_id, holder_kind, holder_id, provider, provider_ref, period_start, "
              "period_end, amount_minor, currency) VALUES (%s,%s,%s,'google_play',%s,%s,%s,499,'GBP')",
              tenant, kind, holder, f"GPA.{holder}", now - timedelta(days=1), now + timedelta(days=29))


def test_trial_is_30_days_with_full_ads(org):
    admin, user, dev = org
    e = admin.get("/v1/licence").json()
    assert e["state"] == "trial" and e["ad_rate"] == 1.0 and e["trial_days_left"] in (29, 30)
    assert e["price"] == {"amount": "4.99", "currency": "GBP", "period": "P1M", "product_id": "aav_protection_monthly"}
    assert e["console_access"] and e["protection_enabled"]


def test_paid_user_gets_95_percent_fewer_ads(org, admin_sql):
    admin, user, dev = org
    _grant_licence(admin_sql, admin.tenant_id, "user", user.user_id)
    assert user.get("/v1/licence").json()["ad_rate"] == pytest.approx(0.05)
    assert admin.get("/v1/licence").json()["ad_rate"] == 1.0  # admin is not licensed (per_user)
    from app.licensing import AdGate
    full, paid = AdGate(1.0), AdGate(0.05)
    shown_full = sum(full.should_show("dashboard_banner") for _ in range(1000))
    shown_paid = sum(paid.should_show("dashboard_banner") for _ in range(1000))
    assert shown_full == 1000 and shown_paid == 50  # exactly 95% fewer
    assert not AdGate(1.0).should_show("approval_screens")  # never on security decisions


def test_per_device_licensing(org, admin_sql, client):
    admin, user, dev = org
    assert admin.put("/v1/licence/settings", json={"licence_unit": "per_device",
                                                   "post_trial_policy": "paywall_console_keep_protection"}).status_code == 200
    _expire_trial(admin_sql, admin.tenant_id)
    lic = client.get("/v1/agent/licence", headers={"X-Device-Key": dev["device_key"]}).json()
    assert lic["bundle"]["entitlement"]["state"] == "expired"
    _grant_licence(admin_sql, admin.tenant_id, "device", dev["device_id"])
    lic = client.get("/v1/agent/licence", headers={"X-Device-Key": dev["device_key"]}).json()
    assert lic["bundle"]["entitlement"]["state"] == "paid" and lic["bundle"]["entitlement"]["ad_rate"] == 0.05
    assert admin.get("/v1/licence").json()["state"] == "paid"  # console: a device licence is active


@pytest.mark.parametrize("policy,console,protection", [
    ("paywall_console_keep_protection", False, True),
    ("free_with_full_ads", True, True),
    ("lock_all", False, False)])
def test_post_trial_policies(org, admin_sql, client, policy, console, protection):
    admin, user, dev = org
    body = {"licence_unit": "per_user", "post_trial_policy": policy}
    if policy == "lock_all":
        assert admin.put("/v1/licence/settings", json=body).status_code == 409  # must acknowledge
        body["acknowledge_lock_all_disables_protection"] = True
    assert admin.put("/v1/licence/settings", json=body).status_code == 200
    _expire_trial(admin_sql, admin.tenant_id)
    e = admin.get("/v1/licence").json()
    assert (e["state"], e["console_access"], e["protection_enabled"], e["ad_rate"]) == \
        ("expired", console, protection, 1.0)
    devices = admin.get("/v1/devices")
    assert devices.status_code == (200 if console else 402)
    assert admin.get("/v1/auth/me").status_code == 200  # sign-in, licence and billing stay reachable
    ag = client.get("/v1/agent/licence", headers={"X-Device-Key": dev["device_key"]}).json()
    assert ag["bundle"]["entitlement"]["protection_enabled"] is protection


def test_agent_honours_signed_entitlement(org, admin_sql, client, tmp_path, baseline_bundle):
    import sys
    sys.path.insert(0, str(PRODUCT / "agent"))
    from aav_agent.agent import Agent
    admin, user, dev = org
    admin.put("/v1/licence/settings", json={"licence_unit": "per_user", "post_trial_policy": "lock_all",
                                            "acknowledge_lock_all_disables_protection": True})
    token = admin.post("/v1/enrollment-tokens", json={}).json()["token"]
    ag = Agent(str(tmp_path / "s"), http=client)
    ag.enrol(token, "lic-host")
    assert ag.licence_allows_protection() is True
    _expire_trial(admin_sql, admin.tenant_id)
    assert ag.licence_allows_protection() is False
    ag.refresh_policy()
    ag.heartbeat()
    d = next(x for x in admin_sql("SELECT protection_status FROM aav.devices WHERE hostname = 'lic-host'"))
    assert d["protection_status"] == "disabled"


def test_all_supplied_admob_ids_configured_and_fail_closed(client):
    cfg = client.get("/v1/ads/config").json()
    assert cfg["publisher_id"] == "pub-2980680946304710"
    assert cfg["adsense"]["client"] == "ca-pub-2980680946304710"
    apps = {a["app_id"]: [u["id"] for u in a["units"]] for a in cfg["admob"]["apps"]}
    assert apps["ca-app-pub-2980680946304710~3427805116"] == [f"ca-app-pub-2980680946304710/{n}" for n in (
        "6357220784", "7811958596", "3898578402", "8550325196", "2665387781")]
    assert apps["ca-app-pub-2980680946304710~2617421798"] == [f"ca-app-pub-2980680946304710/{n}" for n in (
        "1032845563", "2172884450", "3668921616", "5953999752", "6184281650", "6514576804")]
    assert cfg["admob"]["enabled"] is False and cfg["adsense"]["enabled"] is False
    assert all(u["format"] is None for a in cfg["admob"]["apps"] for u in a["units"])
    assert cfg["ad_rate"] == {"trial": 1.0, "expired": 1.0, "paid": 0.05}


def test_app_ads_txt_matches_publisher():
    txt = (PRODUCT / "monetization" / "app-ads.txt").read_text()
    assert txt == "google.com, pub-2980680946304710, DIRECT, f08c47fec0942fa0\n"


class _Play(httpx.BaseTransport):
    def __init__(self, state="SUBSCRIPTION_STATE_ACTIVE", product="aav_protection_monthly"):
        self.state, self.product = state, product

    def handle_request(self, request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t"})
        end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
        return httpx.Response(200, json={"subscriptionState": self.state, "latestOrderId": "GPA.1234",
                                         "startTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                         "lineItems": [{"productId": self.product, "expiryTime": end,
                                                        "autoRenewingPlan": {"recurringPrice": {
                                                            "currencyCode": "GBP", "units": "4", "nanos": 990000000}}}]})


def test_google_play_receipt_verification(org, tmp_path, monkeypatch):
    admin, user, dev = org
    from app.routers import billing
    body = {"purchase_token": "tok-abcdefghij", "holder_kind": "user", "holder_id": user.user_id}
    assert user.post("/v1/billing/google-play/verify", json=body).status_code == 503  # not configured
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps({"client_email": "svc@example.iam", "private_key": key,
                              "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setenv("AAV_PLAY_SERVICE_ACCOUNT_FILE", str(sa))
    billing.set_play_transport(_Play(state="SUBSCRIPTION_STATE_EXPIRED"))
    assert user.post("/v1/billing/google-play/verify", json=body).status_code == 402
    billing.set_play_transport(_Play())
    try:
        r = user.post("/v1/billing/google-play/verify", json=body)
        assert r.status_code == 201, r.text
        assert user.get("/v1/licence").json()["state"] == "paid"
        other = dict(body, holder_id=admin.user_id)
        assert user.post("/v1/billing/google-play/verify", json=other).status_code == 403
    finally:
        billing.set_play_transport(None)
    assert user.post("/v1/billing/app-store/verify").status_code == 503
    assert user.post("/v1/billing/web/checkout").status_code == 503
