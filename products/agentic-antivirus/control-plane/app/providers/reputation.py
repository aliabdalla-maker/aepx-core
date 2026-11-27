"""URL reputation and phishing feeds (SEC-02): look a URL up in live threat-intelligence services.

URLhaus (abuse.ch): POST https://urlhaus-api.abuse.ch/v1/url/ (form url=...), header Auth-Key.
Google Safe Browsing v4 Lookup API: POST https://safebrowsing.googleapis.com/v4/threatMatches:find?key=KEY.
Both return {"malicious": bool, "threat": str|None, "source": provider, "details": {...}}.
"""
from __future__ import annotations

from app.providers.base import Provider, ProviderError

CLIENT = {"clientId": "agentic-antivirus", "clientVersion": "0.1.2"}


class UrlHaus(Provider):
    kind, name = "url_reputation", "urlhaus"
    hosts = ("urlhaus-api.abuse.ch",)
    API = "https://urlhaus-api.abuse.ch/v1"

    def _h(self) -> dict:
        return {"Auth-Key": self.secret}

    def health(self) -> dict:
        r = self._check(self.http.get(f"{self.API}/urls/recent/limit/1/", headers=self._h()), "health")
        if r.json().get("query_status") != "ok":
            raise ProviderError(f"urlhaus: {r.json().get('query_status')}")
        return {"ok": True, "detail": "urlhaus reachable with this key"}

    def lookup(self, url: str) -> dict:
        r = self._check(self.http.post(f"{self.API}/url/", headers=self._h(), data={"url": url}), "lookup")
        b = r.json()
        status = b.get("query_status")
        if status == "no_results":
            return {"malicious": False, "threat": None, "source": self.name, "details": {}}
        if status != "ok":
            raise ProviderError(f"urlhaus: {status}")
        return {"malicious": True, "threat": b.get("threat") or "malware_download", "source": self.name,
                "details": {"url_status": b.get("url_status"), "tags": b.get("tags"),
                            "reference": b.get("urlhaus_reference"), "date_added": b.get("date_added")}}


class GoogleSafeBrowsing(Provider):
    kind, name = "url_reputation", "google_safe_browsing"
    hosts = ("safebrowsing.googleapis.com",)
    API = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

    def _find(self, url: str) -> dict:
        r = self._check(self.http.post(self.API, params={"key": self.secret}, json={
            "client": CLIENT, "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}]}}),
            "lookup")
        return r.json()

    def health(self) -> dict:
        self._find("https://www.example.com/")
        return {"ok": True, "detail": "safe browsing reachable with this key"}

    def lookup(self, url: str) -> dict:
        matches = self._find(url).get("matches", [])
        return {"malicious": bool(matches), "threat": matches[0]["threatType"] if matches else None,
                "source": self.name, "details": {"matches": len(matches)}}
