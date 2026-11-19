from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_aggregates_all_services():
    resp = client.get("/health")
    body = resp.json()
    # every downstream is unreachable in a unit-test context, so each
    # should report "down" rather than the endpoint itself erroring out.
    assert "registry" in body
    assert body["registry"]["status"] == "down"


def test_health_includes_marketplace_and_billing():
    # compose passes MARKETPLACE_URL / BILLING_URL to the gateway; both must
    # be polled so the aggregate (and the gateway.health conformance check)
    # covers them.
    body = client.get("/health").json()
    assert body["marketplace"]["status"] == "down"
    assert body["billing"]["status"] == "down"


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _fake_client(scores=None, optimiser_down=False, calls=None):
    """Stand-in for httpx.AsyncClient: Registry returns an agent, Cost
    Optimiser returns the given utility score per candidate route."""
    scores = scores or {}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kw):
            return _Resp({"agent_id": url.rsplit("/", 1)[-1], "name": "demo"})

        async def post(self, url, json=None, **kw):
            if calls is not None:
                calls.append((url, json))
            if optimiser_down:
                raise ConnectionError("connection refused")
            c = json["candidate_route"]
            return _Resp({"candidate_route": c, "utility_score": scores.get(c, 0.5), "explanation": f"{c} ok"})

    return FakeClient


def test_execute_picks_highest_utility_route(monkeypatch):
    import app.main as main

    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client({"cache": 0.6, "small_model": 0.7, "large_model": 0.4}, calls=calls))
    body = client.post("/execute", params={"agent_id": "a1", "capability": "generate"}, json={"prompt": "hi"}).json()
    # existing response shape is preserved for the SDK
    assert body["agent"]["agent_id"] == "a1"
    assert body["payload"] == {"prompt": "hi"}
    assert body["route"]["status"] == "decided"
    assert body["route"]["selected"] == "small_model"
    assert [j["candidate_route"] for _, j in calls] == main.DEFAULT_CANDIDATES
    assert all(u.endswith("/route/decide") for u, _ in calls)


def test_execute_tie_goes_to_cheaper_tier(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client({"cache": 0.5, "small_model": 0.5, "large_model": 0.5}))
    body = client.post("/execute", params={"agent_id": "a1", "capability": "generate"}, json={}).json()
    assert body["route"]["selected"] == "cache"


def test_execute_pinned_route_scores_only_that_route(monkeypatch):
    import app.main as main

    calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client(calls=calls))
    body = client.post("/execute", params={"agent_id": "a1", "capability": "generate", "route": "knowledge"}, json={}).json()
    assert body["route"]["selected"] == "knowledge"
    assert len(calls) == 1


def test_execute_rejects_unknown_route():
    resp = client.post("/execute", params={"agent_id": "a1", "capability": "generate", "route": "gpu_farm"}, json={})
    assert resp.status_code == 422


def test_execute_degrades_when_cost_optimiser_down(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.httpx, "AsyncClient", _fake_client(optimiser_down=True))
    resp = client.post("/execute", params={"agent_id": "a1", "capability": "generate"}, json={})
    assert resp.status_code == 200
    assert resp.json()["route"]["status"] == "unavailable"
    assert resp.json()["agent"]["agent_id"] == "a1"
