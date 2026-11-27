"""B-06 live provider adapters: each adapter's requests match the provider's documented API (method, URL, auth,
body) and its responses are interpreted correctly, including refusals; then the whole governed path — stored
credential, live credential check, verified_live promotion, approval, provider apply and rollback — end to end.
The providers' APIs are stood in for by an httpx MockTransport that enforces their auth and payload contracts."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import providers
from app.providers import Cloudflare, ProviderError, Unsupported
from app.providers.identity import EntraId, GoogleWorkspace
from app.providers.network import OPNsense
from app.providers.reputation import GoogleSafeBrowsing, UrlHaus
from app.providers.storage import S3Backup
from app.routers import integrations

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()).decode()
SA = json.dumps({"client_email": "aav@proj.iam.gserviceaccount.com", "private_key": PEM, "private_key_id": "k1",
                 "token_uri": "https://oauth2.googleapis.com/token"})


class FakeProviders:
    """Contract-enforcing stand-in for the provider APIs used by the adapters."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.cf_rules: dict[str, dict] = {}
        self.cf_level = "medium"
        self.opn_alias: set[str] = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        h, path, m = req.url.host, req.url.path, req.method
        js = lambda code, body: httpx.Response(code, json=body)  # noqa: E731
        if h == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            claims = jwt.decode(form["assertion"], KEY.public_key(), algorithms=["RS256"],
                                audience="https://oauth2.googleapis.com/token")
            assert form["grant_type"] == "urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
            assert claims["sub"] == "admin@corp.example" and claims["scope"].endswith("admin.directory.user")
            return js(200, {"access_token": "g-token", "expires_in": 3600})
        if h == "admin.googleapis.com":
            assert req.headers["authorization"] == "Bearer g-token"
            user = path.split("/users/")[1].split("/")[0]
            if user == "ghost%40corp.example" or user == "ghost@corp.example":
                return js(404, {"error": {"message": "Resource Not Found: userKey"}})
            if m == "PATCH":
                assert json.loads(req.content) == {"suspended": True}
                return js(200, {"primaryEmail": user, "suspended": True})
            if m == "POST" and path.endswith("/signOut"):
                return httpx.Response(204)
            return js(200, {"primaryEmail": "admin@corp.example"})
        if h == "login.microsoftonline.com":
            assert "client_secret=entra-secret" in req.content.decode()
            return js(200, {"access_token": "e-token"})
        if h == "graph.microsoft.com":
            assert req.headers["authorization"] == "Bearer e-token"
            if m == "PATCH":
                assert json.loads(req.content) == {"accountEnabled": False}
                return httpx.Response(204)
            if path.endswith("/revokeSignInSessions"):
                return js(200, {"value": True})
            return js(200, {"value": [{"displayName": "Corp"}]})
        if h == "api.cloudflare.com":
            if req.headers.get("authorization") != "Bearer cf-token":
                return js(403, {"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}]})
            if path.endswith("/user/tokens/verify"):
                return js(200, {"success": True, "result": {"status": "active"}})
            if path.endswith("/settings/security_level"):
                if m == "PATCH":
                    self.cf_level = json.loads(req.content)["value"]
                return js(200, {"success": True, "result": {"id": "security_level", "value": self.cf_level}})
            if "/firewall/access_rules/rules" in path:
                if m == "POST":
                    b = json.loads(req.content)
                    assert b["mode"] == "block" and b["notes"].startswith("aav:")
                    assert b["configuration"]["target"] in ("ip", "ip_range", "country")
                    rid = f"r{len(self.cf_rules) + 1}"
                    self.cf_rules[rid] = b
                    return js(200, {"success": True, "result": {"id": rid}})
                if m == "DELETE":
                    rid = path.rsplit("/", 1)[1]
                    self.cf_rules.pop(rid)
                    return js(200, {"success": True, "result": {"id": rid}})
            if path.endswith("/zones/zone-1"):
                return js(200, {"success": True, "result": {"id": "zone-1"}})
            return js(404, {"success": False, "errors": [{"message": "not found"}]})
        if h == "fw.corp.example":
            auth = base64.b64decode(req.headers["authorization"].split()[1]).decode()
            assert auth == "key1:sec1"
            if "/alias_util/add/" in path:
                self.opn_alias.add(json.loads(req.content)["address"])
                return js(200, {"status": "done"})
            if "/alias_util/delete/" in path:
                self.opn_alias.discard(json.loads(req.content)["address"])
                return js(200, {"status": "done"})
            return js(200, {"rows": [{"ip": a} for a in self.opn_alias]})
        if h == "urlhaus-api.abuse.ch":
            assert req.headers["auth-key"] == "uh-key"
            if path.endswith("/url/"):
                url = dict(x.split("=", 1) for x in req.content.decode().split("&"))["url"]
                if "evil" in url:
                    return js(200, {"query_status": "ok", "threat": "malware_download", "url_status": "online",
                                    "urlhaus_reference": "https://urlhaus.abuse.ch/url/1/", "tags": ["exe"]})
                return js(200, {"query_status": "no_results"})
            return js(200, {"query_status": "ok", "urls": []})
        if h == "safebrowsing.googleapis.com":
            assert req.url.params["key"] == "gsb-key"
            body = json.loads(req.content)
            url = body["threatInfo"]["threatEntries"][0]["url"]
            return js(200, {"matches": [{"threatType": "SOCIAL_ENGINEERING"}]} if "phish" in url else {})
        if h == "backups.corp.example":
            assert req.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/")
            fresh = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            old = (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            items = [("nightly/db-old.tar.zst", old, 900)]
            if req.url.params["prefix"] != "stale/":
                items.append(("nightly/db-new.tar.zst", fresh, 1200))
            xml = '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">' + "".join(
                f"<Contents><Key>{k}</Key><LastModified>{t}</LastModified><Size>{s}</Size></Contents>"
                for k, t, s in items) + "</ListBucketResult>"
            return httpx.Response(200, content=xml.encode(), headers={"content-type": "application/xml"})
        return js(599, {"unexpected": str(req.url)})


@pytest.fixture
def fake():
    return FakeProviders()


def mk(cls, fake, config, secret, **kw):
    return cls(config, secret, http=httpx.Client(transport=httpx.MockTransport(fake)), check_egress=False, **kw)


def test_identity_adapters(fake):
    g = mk(GoogleWorkspace, fake, {"admin_email": "admin@corp.example"}, SA)
    assert g.health()["ok"]
    assert g.execute("suspend_account", "bob@corp.example")["status"] == "completed"
    assert g.execute("revoke_sessions", "bob@corp.example")["provider_result"] == {"signed_out": True}
    with pytest.raises(ProviderError, match="404"):
        g.execute("suspend_account", "ghost@corp.example")
    e = mk(EntraId, fake, {"tenant_id": "t1", "client_id": "c1"}, "entra-secret")
    assert e.health()["detail"] == "tenant Corp reachable"
    assert e.execute("suspend_account", "bob@corp.example")["provider_result"] == {"accountEnabled": False}
    assert e.execute("revoke_sessions", "bob@corp.example")["status"] == "completed"
    with pytest.raises(Unsupported):
        e.execute("delete_user", "bob@corp.example")


def test_cloudflare_apply_and_rollback(fake):
    cf = mk(Cloudflare, fake, {"zone_id": "zone-1"}, "cf-token")
    assert cf.health()["ok"]
    ref = cf.apply({"id": "tp1", "control": "ip_block", "config": {"values": ["203.0.113.7", "198.51.100.0/24"]}})
    assert len(ref["rule_ids"]) == 2
    assert {r["configuration"]["target"] for r in fake.cf_rules.values()} == {"ip", "ip_range"}
    cf.rollback({"id": "tp1", "config": {"provider_ref": ref}})
    assert fake.cf_rules == {}
    ref = cf.apply({"id": "tp2", "control": "challenge", "config": {}})
    assert fake.cf_level == "under_attack" and ref["previous_security_level"] == "medium"
    cf.rollback({"id": "tp2", "config": {"provider_ref": ref}})
    assert fake.cf_level == "medium"
    with pytest.raises(Unsupported):
        cf.apply({"id": "tp3", "control": "rate_limit", "config": {}})
    with pytest.raises(ProviderError, match="Invalid access token"):
        mk(Cloudflare, fake, {"zone_id": "zone-1"}, "wrong").health()


def test_opnsense_reputation_and_backup(fake):
    fw = mk(OPNsense, fake, {"alias": "aav_block"}, "key1:sec1", endpoint="https://fw.corp.example")
    ref = fw.apply({"id": "x", "control": "ip_block", "config": {"values": ["203.0.113.9"]}})
    assert fake.opn_alias == {"203.0.113.9"} and "1 entries" in fw.health()["detail"]
    fw.rollback({"config": {"provider_ref": ref}})
    assert fake.opn_alias == set()
    with pytest.raises(ProviderError, match="API_KEY:API_SECRET"):
        mk(OPNsense, fake, {}, "nocolon", endpoint="https://fw.corp.example").health()
    uh = mk(UrlHaus, fake, {}, "uh-key")
    assert uh.lookup("http://evil.example/a.exe")["threat"] == "malware_download"
    assert uh.lookup("https://ok.example/")["malicious"] is False and uh.health()["ok"]
    gsb = mk(GoogleSafeBrowsing, fake, {}, "gsb-key")
    assert gsb.lookup("http://phish.example/login") == {"malicious": True, "threat": "SOCIAL_ENGINEERING",
                                                        "source": "google_safe_browsing", "details": {"matches": 1}}
    cfg = {"endpoint": "https://backups.corp.example", "region": "eu-west-2", "bucket": "b", "prefix": "nightly/"}
    ok = mk(S3Backup, fake, cfg, "AK:SK").verify_backup("item-1")
    assert ok["verified"] is True and ok["object"] == "nightly/db-new.tar.zst" and ok["age_hours"] < 4
    stale = mk(S3Backup, fake, {**cfg, "prefix": "stale/"}, "AK:SK").verify_backup("item-1")
    assert stale["verified"] is False and "h old" in stale["reason"]


def test_adapters_refuse_without_credentials_and_check_egress():
    with pytest.raises(ProviderError, match="no credential"):
        Cloudflare({"zone_id": "z"}, "")
    with pytest.raises(ProviderError, match="egress denied"):
        Cloudflare({"zone_id": "z"}, "t")                       # api.cloudflare.com not on the test allowlist


@pytest.fixture
def live(fake, monkeypatch):
    monkeypatch.setattr(integrations, "TEST_TRANSPORT", httpx.MockTransport(fake))
    return fake


def test_governed_traffic_policy_applies_and_rolls_back_through_cloudflare(new_account, invite, live, admin_sql):
    admin = new_account("cf")
    analyst = invite(admin, "security_analyst")
    integ = admin.post("/v1/integrations", json={"name": "cloudflare", "signal_kind": "waf", "protocol": "rest",
                                                 "config": {"zone_id": "zone-1", "provider": "cloudflare"}}).json()
    iid = integ["id"]
    promote = {"maturity": "verified_live", "provider": "cloudflare",
               "evidence": {"sandbox_contract_passed": True, "policy_reviewed": True}}
    assert admin.post(f"/v1/integrations/{iid}/maturity", json=promote).status_code == 409   # no credential yet
    assert admin.put(f"/v1/integrations/{iid}/secret", json={"value": "cf-token"}).status_code == 204
    stored = admin_sql("SELECT ciphertext FROM aav.integration_secrets WHERE integration_id = %s", iid)[0]
    assert b"cf-token" not in bytes(stored["ciphertext"])                                      # encrypted at rest
    assert "cf-token" not in json.dumps(admin.get("/v1/integrations").json())                   # never returned
    assert admin.post(f"/v1/integrations/{iid}/maturity", json=promote).status_code == 409   # not checked live yet
    chk = admin.post(f"/v1/integrations/{iid}/verify-credentials").json()
    assert chk["ok"] is True, chk
    assert admin.post(f"/v1/integrations/{iid}/maturity", json=promote).status_code == 200
    r = analyst.post("/v1/traffic-policies", json={"service": "shop", "control": "ip_block",
                                                   "config": {"values": ["203.0.113.66"]}, "reason": "L7 flood source"})
    tp, act = r.json()["traffic_policy_id"], r.json()["action"]
    assert admin.post(f"/v1/actions/{act['id']}/approve", json={}).status_code == 200
    out = admin.post(f"/v1/actions/{act['id']}/dispatch").json()
    assert out["commands"][0]["status"] == "active", out
    assert [r["configuration"]["value"] for r in live.cf_rules.values()] == ["203.0.113.66"]
    rb = analyst.post(f"/v1/traffic-policies/{tp}/rollback").json()
    assert admin.post(f"/v1/actions/{rb['id']}/approve", json={}).status_code == 200
    out = admin.post(f"/v1/actions/{rb['id']}/dispatch").json()
    assert out["commands"][0]["status"] == "rolled_back", out
    assert live.cf_rules == {}
    pol = next(t for t in admin.get("/v1/traffic-policies").json() if t["id"] == tp)
    assert pol["status"] == "rolled_back" and pol["config"]["provider_ref"]["rule_ids"]


def test_url_reputation_combines_bundle_and_live_feeds(new_account, live, baseline_bundle):
    admin = new_account("urlrep")
    integ = admin.post("/v1/integrations", json={"name": "urlhaus", "signal_kind": "url_reputation", "protocol": "rest",
                                                 "config": {"provider": "urlhaus"}}).json()
    admin.put(f"/v1/integrations/{integ['id']}/secret", json={"value": "uh-key"})
    assert admin.post(f"/v1/integrations/{integ['id']}/verify-credentials").json()["ok"]
    admin.post(f"/v1/integrations/{integ['id']}/maturity", json={
        "maturity": "verified_live", "provider": "urlhaus",
        "evidence": {"sandbox_contract_passed": True, "policy_reviewed": True}})
    bad = admin.post("/v1/url-reputation", json={"url": "http://evil.example/payload.exe"}).json()
    assert bad["verdict"] == "malicious" and {r["source"] for r in bad["results"]} >= {"urlhaus"}
    assert admin.post("/v1/url-reputation", json={"url": "https://fine.example/"}).json()["verdict"] == "not_listed"


def test_identity_action_reports_provider_refusal_as_failure(new_account, live):
    admin = new_account("idp")
    integ = admin.post("/v1/integrations", json={"name": "gws", "signal_kind": "identity", "protocol": "rest",
                                                 "config": {"provider": "google_workspace",
                                                            "admin_email": "admin@corp.example"}}).json()
    admin.put(f"/v1/integrations/{integ['id']}/secret", json={"value": SA})
    assert admin.post(f"/v1/integrations/{integ['id']}/verify-credentials").json()["ok"]
    admin.post(f"/v1/integrations/{integ['id']}/maturity", json={
        "maturity": "verified_live", "provider": "google_workspace",
        "evidence": {"sandbox_contract_passed": True, "policy_reviewed": True}})
    from app import db
    from app.routers.integrations import execute_identity_action
    with db.tenant_tx(admin.tenant_id) as cur:
        ok = execute_identity_action(cur, admin.tenant_id, integ["id"], "suspend_account", "bob@corp.example")
        bad = execute_identity_action(cur, admin.tenant_id, integ["id"], "suspend_account", "ghost@corp.example")
    assert ok["status"] == "completed"
    assert bad["status"] == "failed" and "404" in bad["reason"]
    assert ("identity", "google_workspace") in providers.REGISTRY
