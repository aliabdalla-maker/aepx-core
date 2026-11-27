"""Common provider plumbing: egress-checked HTTP client, errors, outcome shape."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx


class ProviderError(RuntimeError):
    """The provider refused or failed the call (bad credentials, not found, HTTP error)."""


class Unsupported(ProviderError):
    """The provider has no way to do what was asked; nothing was changed."""


class Provider:
    kind = ""
    name = ""
    hosts: tuple[str, ...] = ()            # fixed API hosts; endpoint-based providers check their endpoint instead

    def __init__(self, config: dict, secret: str, *, endpoint: str = "", http: httpx.Client | None = None,
                 check_egress: bool = True):
        self.config, self.secret, self.endpoint = config or {}, secret or "", endpoint.rstrip("/")
        if not self.secret:
            raise ProviderError("no credential stored for this integration (PUT /v1/integrations/{id}/secret)")
        if check_egress:
            from app import netpolicy
            targets = [f"https://{h}" for h in self.hosts] or ([self.endpoint] if self.endpoint else [])
            for t in targets:
                try:
                    netpolicy.check_endpoint(t, allow_private=bool(self.config.get("private_network_approved")))
                except netpolicy.EgressDenied as exc:
                    raise ProviderError(f"egress denied: {exc}") from exc
        self.http = http or httpx.Client(timeout=20, follow_redirects=False)

    def _check(self, r: httpx.Response, what: str) -> httpx.Response:
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} {what}: HTTP {r.status_code} {r.text[:200]}")
        return r

    def health(self) -> dict:                                     # pragma: no cover - overridden
        raise Unsupported("no health check")

    @staticmethod
    def host_of(url: str) -> str:
        return urlparse(url).hostname or ""
