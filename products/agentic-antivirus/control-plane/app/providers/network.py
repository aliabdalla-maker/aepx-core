"""OPNsense firewall (network containment at the perimeter): ip_block adds addresses to an alias that a block rule
uses; rollback removes them. API key + secret (System > Access > Users > API keys), sent as HTTP basic auth.
Setup on the firewall: create alias config.alias (type Host(s)) and a block rule that uses it.
  POST {endpoint}/api/firewall/alias_util/add/{alias}    {"address": "203.0.113.7"}
  POST {endpoint}/api/firewall/alias_util/delete/{alias} {"address": "203.0.113.7"}
  GET  {endpoint}/api/firewall/alias_util/list/{alias}   (health)
"""
from __future__ import annotations

from urllib.parse import quote

from app.providers.base import Provider, ProviderError, Unsupported


class OPNsense(Provider):
    kind, name = "firewall", "opnsense"

    def _auth(self) -> tuple[str, str]:
        key, _, secret = self.secret.partition(":")
        if not key or not secret:
            raise ProviderError('credential must be "API_KEY:API_SECRET"')
        return key, secret

    @property
    def _alias(self) -> str:
        return quote(self.config.get("alias") or "aav_blocklist")

    def health(self) -> dict:
        if not self.endpoint:
            raise ProviderError("needs the firewall endpoint URL")
        r = self._check(self.http.get(f"{self.endpoint}/api/firewall/alias_util/list/{self._alias}", auth=self._auth()),
                        "health")
        return {"ok": True, "detail": f"alias {self.config.get('alias') or 'aav_blocklist'} has "
                                      f"{len(r.json().get('rows', []))} entries"}

    def apply(self, tp: dict) -> dict:
        if tp["control"] != "ip_block":
            raise Unsupported(f"opnsense adapter does not implement '{tp['control']}'; nothing was changed")
        added = []
        for ip in (tp.get("config") or {}).get("values") or []:
            r = self._check(self.http.post(f"{self.endpoint}/api/firewall/alias_util/add/{self._alias}",
                                           auth=self._auth(), json={"address": ip}), f"add {ip}")
            if r.json().get("status") not in ("done", "ok"):
                raise ProviderError(f"opnsense refused {ip}: {r.text[:200]}")
            added.append(ip)
        if not added:
            raise ProviderError("config.values is empty")
        return {"provider": "opnsense", "alias": self.config.get("alias") or "aav_blocklist", "addresses": added}

    def rollback(self, tp: dict) -> dict:
        ref = (tp.get("config") or {}).get("provider_ref") or {}
        for ip in ref.get("addresses", []):
            self._check(self.http.post(f"{self.endpoint}/api/firewall/alias_util/delete/{self._alias}",
                                       auth=self._auth(), json={"address": ip}), f"delete {ip}")
        return {"provider": "opnsense", "removed": ref.get("addresses", [])}
