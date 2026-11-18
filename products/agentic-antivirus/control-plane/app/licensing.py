"""Trial, subscription entitlement and ad-rate policy.

Owner requirements (18 Nov 2026):
  * 30 days free with AdMob (apps) and AdSense (web) at 100% ad rate.
  * GBP 4.99 per month per user or per download (device) - tenant chooses the licence unit.
  * After payment, ads reduced by 95% (ad rate 0.05).
  * After the trial without payment, the tenant chooses one of three policies:
      paywall_console_keep_protection | free_with_full_ads | lock_all
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CONFIG_PATH = Path(os.getenv("AAV_ADS_CONFIG", Path(__file__).resolve().parents[2] / "monetization" / "ads-config.json"))


def ads_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def ad_rate(state: str) -> float:
    return float(ads_config()["ad_rate"][state])


def entitlement(cur, *, tenant_id, user_id=None, device_id=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cur.execute("SELECT * FROM aav.subscriptions WHERE tenant_id = %s", (tenant_id,))
    sub = cur.fetchone()
    if not sub:
        raise LookupError("subscription row missing")
    trial_end = sub["trial_started_at"] + timedelta(days=sub["trial_days"])
    unit = sub["licence_unit"]
    if unit == "per_user":
        if device_id and not user_id:
            cur.execute("SELECT owner_user_id FROM aav.devices WHERE id = %s", (device_id,))
            r = cur.fetchone()
            user_id = r["owner_user_id"] if r else None
        cur.execute("SELECT period_end FROM aav.licences WHERE holder_kind = 'user' AND holder_id = %s "
                    "AND status = 'active' AND period_start <= %s AND period_end > %s ORDER BY period_end DESC LIMIT 1",
                    (user_id, now, now))
    elif device_id:
        cur.execute("SELECT period_end FROM aav.licences WHERE holder_kind = 'device' AND holder_id = %s "
                    "AND status = 'active' AND period_start <= %s AND period_end > %s ORDER BY period_end DESC LIMIT 1",
                    (device_id, now, now))
    else:
        # web console under per-device licensing: paid while at least one device licence is active
        cur.execute("SELECT max(period_end) AS period_end FROM aav.licences WHERE holder_kind = 'device' "
                    "AND status = 'active' AND period_start <= %s AND period_end > %s", (now, now))
    lic = cur.fetchone()
    paid_until = lic["period_end"] if lic and lic["period_end"] else None
    if paid_until:
        state = "paid"
    elif now < trial_end:
        state = "trial"
    else:
        state = "expired"
    policy = sub["post_trial_policy"]
    console = state != "expired" or policy == "free_with_full_ads"
    protection = state != "expired" or policy != "lock_all"
    cfg = ads_config()
    return {
        "state": state, "licence_unit": unit, "post_trial_policy": policy,
        "trial_started_at": sub["trial_started_at"].isoformat(), "trial_ends_at": trial_end.isoformat(),
        "trial_days_left": max(0, (trial_end - now).days) if state == "trial" else 0,
        "paid_until": paid_until.isoformat() if paid_until else None,
        "ad_rate": ad_rate(state), "console_access": console, "protection_enabled": protection,
        "price": {"amount": cfg["pricing"]["amount"], "currency": cfg["pricing"]["currency"],
                  "period": cfg["pricing"]["period"], "product_id": cfg["pricing"]["store_product_id"]},
    }


class AdGate:
    """Deterministic ad pacing: with rate r, show an ad on opportunity n when floor(n*r) increases.
    r=1.0 -> every eligible opportunity (100%); r=0.05 -> 1 in 20 (95% fewer)."""

    def __init__(self, rate: float):
        if not 0.0 <= rate <= 1.0:
            raise ValueError("rate must be within [0, 1]")
        self.rate = rate
        self.n = 0

    def should_show(self, placement: str) -> bool:
        cfg = ads_config()["placements"]
        if placement not in cfg["allowed"]:
            return False
        before = int(self.n * self.rate)
        self.n += 1
        return int(self.n * self.rate) > before
