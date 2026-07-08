import os
from pathlib import Path

os.environ["CATALOGUE_PATH"] = str(Path(__file__).resolve().parents[2] / "connectors" / "catalogue.json")

from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)


def test_health_lists_100_connectors():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["connector_count"] == 100
    assert len(body["categories"]) == 10


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeAsyncClient:
    adjust_calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, *args, **kwargs):
        if "/trust/" in url:
            return _FakeResponse({"trust_score": 90})
        raise AssertionError(f"unexpected GET {url}")

    async def post(self, url, *args, **kwargs):
        if "/policy/evaluate" in url:
            risk = kwargs.get("params", {}).get("risk_level", "")
            # mirror Governance's seed policy: S0-S2 (R0-R2) allowed, S3+ denied
            allowed = risk in ("AIA-R0", "AIA-R1", "AIA-R2")
            return _FakeResponse({"allowed": allowed})
        if "/connector/execute" in url:
            # regression guard: a real model call needs real headroom — the
            # client's default 3s (sized for in-memory trust/policy lookups)
            # must not silently apply to this call too.
            assert kwargs.get("timeout", 0) >= 15.0, "connector forward must override the client's short default timeout"
            return _FakeResponse({"result": "ok"})
        if "/adjust" in url:
            _FakeAsyncClient.adjust_calls.append((url, kwargs.get("json")))
            return _FakeResponse({"trust_score": 91})
        raise AssertionError(f"unexpected POST {url}")


def test_route_allows_trusted_agent(monkeypatch):
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.adjust_calls.clear()
    resp = client.post(
        "/bus/route",
        json={
            "sender": "aepx://agent/tutor-1",
            "receiver": "aepx://connector/salesforce",
            "payload": {"op": "lookup_contact"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connector"] == "salesforce"
    assert body["category"] == "enterprise"
    assert body["trust_score_at_call_time"] == 90
    # a successful invocation must nudge behaviour trust up — otherwise
    # every agent sits at the same default score forever
    assert len(_FakeAsyncClient.adjust_calls) == 1
    assert _FakeAsyncClient.adjust_calls[0][1] == {"component": "behaviour", "delta": 1}


def test_route_stub_connector_from_catalogue(monkeypatch):
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    resp = client.post(
        "/bus/route",
        json={"sender": "aepx://agent/tutor-1", "receiver": "aepx://connector/pinecone", "payload": {"op": "query"}},
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "data"
    assert resp.json()["maturity"] == "stub"


def test_route_denies_high_risk_connector_by_policy(monkeypatch):
    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    resp = client.post(
        "/bus/route",
        json={"sender": "aepx://agent/tutor-1", "receiver": "aepx://connector/opcua", "payload": {"op": "read_tag"}},
    )
    # opcua is AIA-R3 — denied under the default max_risk_level=S2 policy,
    # which is the governance gate SOA-Architecture.md §4 requires for
    # industrial connectors.
    assert resp.status_code == 403


def test_get_producer_degrades_without_kafka():
    # No broker in the unit-test environment — must return None, not raise.
    main._producer = None
    assert main._get_producer() is None


def test_route_rejects_unknown_connector():
    resp = client.post(
        "/bus/route",
        json={"sender": "aepx://agent/tutor-1", "receiver": "aepx://connector/does-not-exist", "payload": {}},
    )
    assert resp.status_code == 404
