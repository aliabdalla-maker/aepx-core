"""Identity providers (SEC-01, VIS-02): suspend an account and revoke its sessions.

Google Workspace — Admin SDK Directory API with a service account using domain-wide delegation
  (scope https://www.googleapis.com/auth/admin.directory.user, impersonating config.admin_email):
  PATCH /admin/directory/v1/users/{userKey} {"suspended": true}; POST /admin/directory/v1/users/{userKey}/signOut
Microsoft Entra ID — Microsoft Graph with an app registration (User.ReadWrite.All or User.EnableDisableAccount.All
  + User.RevokeSessions.All, application permissions): PATCH /v1.0/users/{id} {"accountEnabled": false};
  POST /v1.0/users/{id}/revokeSignInSessions
"""
from __future__ import annotations

import json
import time
from urllib.parse import quote

import jwt

from app.providers.base import Provider, ProviderError, Unsupported

ACTIONS = ("suspend_account", "revoke_sessions")


class GoogleWorkspace(Provider):
    kind, name = "identity", "google_workspace"
    hosts = ("admin.googleapis.com", "oauth2.googleapis.com")
    API = "https://admin.googleapis.com/admin/directory/v1"
    SCOPE = "https://www.googleapis.com/auth/admin.directory.user"

    def _token(self) -> str:
        try:
            sa = json.loads(self.secret)
            subject = self.config["admin_email"]
        except (ValueError, KeyError) as exc:
            raise ProviderError("needs a service-account JSON credential and config.admin_email") from exc
        now = int(time.time())
        assertion = jwt.encode({"iss": sa["client_email"], "sub": subject, "scope": self.SCOPE,
                                "aud": sa.get("token_uri", "https://oauth2.googleapis.com/token"),
                                "iat": now, "exp": now + 600}, sa["private_key"], algorithm="RS256",
                               headers={"kid": sa.get("private_key_id")})
        r = self._check(self.http.post(sa.get("token_uri", "https://oauth2.googleapis.com/token"), data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}), "token")
        return r.json()["access_token"]

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    def health(self) -> dict:
        r = self._check(self.http.get(f"{self.API}/users/{quote(self.config.get('admin_email', ''))}",
                                      headers=self._h()), "health")
        return {"ok": True, "detail": f"directory reachable as {r.json().get('primaryEmail')}"}

    def execute(self, action: str, target: str) -> dict:
        h, user = self._h(), quote(target)
        if action == "suspend_account":
            r = self._check(self.http.patch(f"{self.API}/users/{user}", headers=h, json={"suspended": True}), action)
            return {"target": target, "status": "completed", "provider_result": {"suspended": r.json().get("suspended")}}
        if action == "revoke_sessions":
            self._check(self.http.post(f"{self.API}/users/{user}/signOut", headers=h), action)
            return {"target": target, "status": "completed", "provider_result": {"signed_out": True}}
        raise Unsupported(action)


class EntraId(Provider):
    kind, name = "identity", "entra_id"
    hosts = ("login.microsoftonline.com", "graph.microsoft.com")
    API = "https://graph.microsoft.com/v1.0"

    def _token(self) -> str:
        try:
            tenant, client = self.config["tenant_id"], self.config["client_id"]
        except KeyError as exc:
            raise ProviderError("needs config.tenant_id and config.client_id") from exc
        r = self._check(self.http.post(f"https://login.microsoftonline.com/{quote(tenant)}/oauth2/v2.0/token", data={
            "client_id": client, "client_secret": self.secret, "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"}), "token")
        return r.json()["access_token"]

    def health(self) -> dict:
        r = self._check(self.http.get(f"{self.API}/organization", headers={"Authorization": f"Bearer {self._token()}"}),
                        "health")
        orgs = r.json().get("value", [])
        return {"ok": True, "detail": f"tenant {orgs[0].get('displayName') if orgs else '?'} reachable"}

    def execute(self, action: str, target: str) -> dict:
        h, user = {"Authorization": f"Bearer {self._token()}"}, quote(target)
        if action == "suspend_account":
            self._check(self.http.patch(f"{self.API}/users/{user}", headers=h, json={"accountEnabled": False}), action)
            return {"target": target, "status": "completed", "provider_result": {"accountEnabled": False}}
        if action == "revoke_sessions":
            r = self._check(self.http.post(f"{self.API}/users/{user}/revokeSignInSessions", headers=h), action)
            return {"target": target, "status": "completed", "provider_result": {"revoked": r.json().get("value", True)}}
        raise Unsupported(action)
