"""Outbound connectors (INT-03 messaging, CRM, ITSM): every console notification (critical alerts, approvals,
incident changes) is also delivered to the tenant's verified_live outbound integrations.

| kind | provider | what it does | credential |
|---|---|---|---|
| messaging | slack | posts to a channel (Incoming Webhook) | the webhook URL |
| messaging | teams | posts to a channel (Teams Workflows / incoming webhook) | the webhook URL |
| crm | hubspot | creates a support ticket (CRM v3 tickets) | private-app access token |
| itsm | servicenow | creates an incident (Table API) | "user:password"; config.instance |

Delivery runs after the database transaction commits, off the request path, with a short timeout; a failed delivery
is recorded on the integration (last_health) and never blocks or rolls back the notification itself.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.providers.base import Provider, ProviderError

SEV_ORDER = {"low": 4, "medium": 3, "high": 2, "critical": 1}


def _text(kind: str, title: str, body: dict) -> str:
    extra = ", ".join(f"{k}: {v}" for k, v in body.items() if v not in (None, "", []) and k != "simulation")
    sim = " [SIMULATION]" if body.get("simulation") else ""
    return f"Agentic Antivirus{sim} — {title}" + (f"\n{extra}" if extra else "") + f"\n({kind})"


class _WebhookChannel(Provider):
    kind = "messaging"
    ALLOWED_HOSTS: tuple[str, ...] = ()

    def __init__(self, config, secret, **kw):
        host = urlparse(secret or "").hostname or ""
        if not any(host == h or host.endswith("." + h) for h in self.ALLOWED_HOSTS):
            raise ProviderError(f"{self.name}: the credential must be a webhook URL on {', '.join(self.ALLOWED_HOSTS)}")
        super().__init__(config, secret, endpoint=secret, **kw)

    def health(self) -> dict:
        self.send("aav.test", "Test message: this channel is connected to Agentic Antivirus.", {})
        return {"ok": True, "detail": "test message delivered"}


class Slack(_WebhookChannel):
    name = "slack"
    ALLOWED_HOSTS = ("hooks.slack.com",)

    def send(self, kind: str, title: str, body: dict) -> dict:
        r = self._check(self.http.post(self.secret, json={"text": _text(kind, title, body)}), "post")
        return {"provider": "slack", "status": r.status_code}


class Teams(_WebhookChannel):
    name = "teams"
    ALLOWED_HOSTS = ("webhook.office.com", "logic.azure.com", "environment.api.powerplatform.com")

    def send(self, kind: str, title: str, body: dict) -> dict:
        card = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                "content": {"type": "AdaptiveCard", "version": "1.4", "$schema":
                            "http://adaptivecards.io/schemas/adaptive-card.json",
                            "body": [{"type": "TextBlock", "wrap": True, "text": _text(kind, title, body)}]}}]}
        r = self._check(self.http.post(self.secret, json=card), "post")
        return {"provider": "teams", "status": r.status_code}


class HubSpot(Provider):
    kind, name = "crm", "hubspot"
    hosts = ("api.hubapi.com",)
    API = "https://api.hubapi.com"

    def _h(self):
        return {"Authorization": f"Bearer {self.secret}"}

    def health(self) -> dict:
        self._check(self.http.get(f"{self.API}/crm/v3/objects/tickets", params={"limit": 1}, headers=self._h()), "health")
        return {"ok": True, "detail": "tickets readable"}

    def send(self, kind: str, title: str, body: dict) -> dict:
        prio = {"critical": "HIGH", "high": "HIGH", "medium": "MEDIUM"}.get(str(body.get("severity", "")), "LOW")
        props = {"subject": f"[Agentic Antivirus] {title}"[:250], "content": _text(kind, title, body)[:5000],
                 "hs_pipeline": self.config.get("pipeline", "0"), "hs_pipeline_stage": self.config.get("stage", "1"),
                 "hs_ticket_priority": prio}
        r = self._check(self.http.post(f"{self.API}/crm/v3/objects/tickets", headers=self._h(),
                                       json={"properties": props}), "create ticket")
        return {"provider": "hubspot", "ticket_id": r.json().get("id")}


class ServiceNow(Provider):
    kind, name = "itsm", "servicenow"

    def __init__(self, config, secret, **kw):
        inst = (config or {}).get("instance", "")
        if not inst or not inst.replace("-", "").isalnum():
            raise ProviderError("needs config.instance (the <instance> in <instance>.service-now.com)")
        super().__init__(config, secret, endpoint=f"https://{inst}.service-now.com", **kw)

    def _auth(self):
        u, _, p = self.secret.partition(":")
        if not u or not p:
            raise ProviderError('credential must be "user:password"')
        return u, p

    def health(self) -> dict:
        self._check(self.http.get(f"{self.endpoint}/api/now/table/incident", params={"sysparm_limit": 1},
                                  auth=self._auth(), headers={"Accept": "application/json"}), "health")
        return {"ok": True, "detail": "incident table readable"}

    def send(self, kind: str, title: str, body: dict) -> dict:
        sev = str(body.get("severity", "medium"))
        lvl = str(min(3, SEV_ORDER.get(sev, 3)))
        r = self._check(self.http.post(f"{self.endpoint}/api/now/table/incident", auth=self._auth(),
                                       headers={"Accept": "application/json"},
                                       json={"short_description": f"[Agentic Antivirus] {title}"[:160],
                                             "description": _text(kind, title, body), "urgency": lvl, "impact": lvl,
                                             "category": self.config.get("category", "security")}), "create incident")
        res = r.json().get("result", {})
        return {"provider": "servicenow", "number": res.get("number"), "sys_id": res.get("sys_id")}


OUTBOUND = {("messaging", "slack"): Slack, ("messaging", "teams"): Teams, ("crm", "hubspot"): HubSpot,
            ("itsm", "servicenow"): ServiceNow}
