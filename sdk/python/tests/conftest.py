"""Shared fake transport — routes aepx.client's httpx.request calls to an
in-test handler keyed on (method, path), so every plugin and conformance
check can be exercised with zero live services (the same no-external-deps
test posture as every services/*/tests suite)."""
import json as jsonlib

import httpx
import pytest

import aepx.client


class FakeAPI:
    """handler registry: (method, path-prefix) -> (status, json-able body)"""

    def __init__(self):
        self.routes = []
        self.calls = []

    def on(self, method, path_prefix, status=200, body=None, body_fn=None):
        self.routes.append((method.upper(), path_prefix, status, body, body_fn))
        return self

    def request(self, method, url, **kwargs):
        parsed = httpx.URL(url)
        path = parsed.path
        self.calls.append((method.upper(), path, kwargs))
        for m, prefix, status, body, body_fn in self.routes:
            if m == method.upper() and path.startswith(prefix):
                payload = body_fn(path, kwargs) if body_fn else body
                if isinstance(payload, tuple):  # body_fn may override the status
                    status, payload = payload
                return httpx.Response(
                    status,
                    content=jsonlib.dumps(payload if payload is not None else {}).encode(),
                    headers={"content-type": "application/json"},
                    request=httpx.Request(method, url),
                )
        raise httpx.ConnectError(f"no fake route for {method} {path}", request=httpx.Request(method, url))


@pytest.fixture
def fake_api(monkeypatch):
    api = FakeAPI()
    monkeypatch.setattr(aepx.client.httpx, "request", api.request)
    return api
