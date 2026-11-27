"""Cloudflare (CDN / WAF / DDoS; DDOS-01, DDOS-03): apply and roll back approved traffic policies on one zone.

Controls (traffic_policies.control):
  ip_block   config {"values": ["203.0.113.7", "198.51.100.0/24"]} -> zone IP Access Rules, mode "block"
  geo_block  config {"values": ["XX", ...]} (ISO 3166-1 alpha-2)  -> zone IP Access Rules, target "country"
  challenge  config {}                                              -> security_level "under_attack" (previous level
                                                                       kept for rollback)
Anything else (rate_limit, bot_control, cache) is refused as unsupported: nothing is changed.
API token permissions: Zone > Firewall Services > Edit, Zone > Zone Settings > Edit, for config.zone_id.
"""
from __future__ import annotations

from urllib.parse import quote

from app.providers.base import Provider, ProviderError, Unsupported


class Cloudflare(Provider):
    kind, name = "cdn", "cloudflare"
    hosts = ("api.cloudflare.com",)
    API = "https://api.cloudflare.com/client/v4"

    @property
    def _zone(self) -> str:
        z = self.config.get("zone_id")
        if not z:
            raise ProviderError("needs config.zone_id")
        return quote(z)

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}"}

    def _call(self, method: str, path: str, what: str, **kw) -> dict:
        r = self.http.request(method, f"{self.API}{path}", headers=self._h(), **kw)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400 or not body.get("success", False):
            errs = "; ".join(e.get("message", "") for e in body.get("errors", [])) or r.text[:200]
            raise ProviderError(f"cloudflare {what}: HTTP {r.status_code} {errs}")
        return body.get("result") or {}

    def health(self) -> dict:
        res = self._call("GET", "/user/tokens/verify", "token verify")
        if res.get("status") != "active":
            raise ProviderError(f"cloudflare token status {res.get('status')}")
        self._call("GET", f"/zones/{self._zone}", "zone read")
        return {"ok": True, "detail": "token active; zone readable"}

    def apply(self, tp: dict) -> dict:
        control, cfg, ref = tp["control"], tp.get("config") or {}, f"aav:{tp['id']}"
        if control in ("ip_block", "geo_block"):
            values = cfg.get("values") or []
            if not values:
                raise ProviderError("config.values is empty")
            rule_ids = []
            for v in values:
                target = "country" if control == "geo_block" else ("ip_range" if "/" in v else "ip")
                res = self._call("POST", f"/zones/{self._zone}/firewall/access_rules/rules", f"{control} {v}", json={
                    "mode": "block", "configuration": {"target": target, "value": v}, "notes": ref})
                rule_ids.append(res["id"])
            return {"provider": "cloudflare", "control": control, "rule_ids": rule_ids}
        if control == "challenge":
            prev = self._call("GET", f"/zones/{self._zone}/settings/security_level", "read security level")
            self._call("PATCH", f"/zones/{self._zone}/settings/security_level", "set under_attack",
                       json={"value": "under_attack"})
            return {"provider": "cloudflare", "control": control, "previous_security_level": prev.get("value")}
        raise Unsupported(f"cloudflare adapter does not implement '{control}'; nothing was changed")

    def rollback(self, tp: dict) -> dict:
        ref = (tp.get("config") or {}).get("provider_ref") or {}
        if ref.get("rule_ids"):
            for rid in ref["rule_ids"]:
                self._call("DELETE", f"/zones/{self._zone}/firewall/access_rules/rules/{quote(rid)}", f"delete {rid}")
            return {"provider": "cloudflare", "deleted_rule_ids": ref["rule_ids"]}
        if "previous_security_level" in ref:
            self._call("PATCH", f"/zones/{self._zone}/settings/security_level", "restore security level",
                       json={"value": ref["previous_security_level"] or "medium"})
            return {"provider": "cloudflare", "security_level": ref["previous_security_level"]}
        raise ProviderError("no provider reference recorded for this policy; nothing to roll back")
