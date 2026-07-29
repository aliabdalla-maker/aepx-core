import io
import os
import tempfile
from pathlib import Path

os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["STATIC_DIR"] = str(Path(__file__).resolve().parents[1] / "static")

from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "console"


def test_gui_served_at_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AEP-X Console" in resp.text


def test_upload_and_list():
    resp = client.post(
        "/api/upload",
        files=[
            ("files", ("notes.txt", io.BytesIO(b"hello aepx"), "text/plain")),
            ("files", ("pic.png", io.BytesIO(b"\x89PNG fake"), "image/png")),
            ("files", ("clip.mp4", io.BytesIO(b"\x00fakevideo"), "video/mp4")),
        ],
    )
    assert resp.status_code == 200
    uploaded = resp.json()["uploaded"]
    kinds = {u["name"]: u["kind"] for u in uploaded}
    assert kinds == {"notes.txt": "file", "pic.png": "image", "clip.mp4": "video"}

    listing = client.get("/api/uploads").json()
    assert len(listing) >= 3

    content = client.get(f"/api/uploads/{uploaded[0]['id']}/content")
    assert content.status_code == 200
    assert content.content == b"hello aepx"


def test_chat_forwards_to_bus(monkeypatch):
    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "connector": "ml", "category": "aiplatform", "maturity": "specialized",
                "ai_risk_class": "AIA-R1", "trust_score_at_call_time": 50,
                "response": {"result": "stub reply", "model": "llama3.2", "confidence": 0.7, "estimated_cost": 0.0},
            }

    class _FakeAsyncClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            assert json["receiver"] == "aepx://connector/ml"
            return _FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    resp = client.post("/api/chat", json={"prompt": "hello", "attachment_ids": []})
    body = resp.json()
    assert body["reply"] == "stub reply"
    assert body["trust_score_at_call_time"] == 50


def test_chat_surfaces_degraded_maturity_not_catalogue_maturity(monkeypatch):
    # Regression: the bus's top-level "maturity" is the static catalogue
    # value ("specialized"); when Ollama falls back mid-call, the adapter's
    # own response carries "specialized_degraded" and that must win — a
    # fallback response must never look identical to a live one.
    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "connector": "ml", "category": "aiplatform", "maturity": "specialized",
                "ai_risk_class": "AIA-R1", "trust_score_at_call_time": 50,
                "response": {
                    "result": "[fallback: unreachable]", "model": "llama3.2:1b",
                    "confidence": 0.3, "estimated_cost": 0.0, "maturity": "specialized_degraded",
                },
            }

    class _FakeAsyncClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            return _FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    resp = client.post("/api/chat", json={"prompt": "hello", "attachment_ids": []})
    assert resp.json()["maturity"] == "specialized_degraded"


def test_agents_ranked_by_live_trust_not_stale_registry_column(monkeypatch):
    # Regression: registry.trust_score is a stale snapshot from creation
    # time; the ranking must use Trust service's live, evolving score.
    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def get(self, url, *a, **k):
            if url.endswith("/agents"):
                return _FakeResponse([
                    {"id": "a1", "name": "low-registry-high-trust", "version": "0.0.1", "trust_score": 0},
                    {"id": "a2", "name": "high-registry-low-trust", "version": "0.0.1", "trust_score": 99},
                ])
            if "/trust/a1" in url:
                return _FakeResponse({"trust_score": 95, "level": "Trusted", "behaviour_score": 95})
            if "/trust/a2" in url:
                return _FakeResponse({"trust_score": 10, "level": "Untrusted", "behaviour_score": 10})
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    ranked = client.get("/api/agents").json()
    assert [a["name"] for a in ranked] == ["low-registry-high-trust", "high-registry-low-trust"]
    assert ranked[0]["trust_score"] == 95


def test_activity_proxies_governance_audit(monkeypatch):
    class _FakeResponse:
        def json(self):
            return [{"topic": "workflow.completed", "event": {"workflow_id": "x"}, "recorded_at": 123.0}]

    class _FakeAsyncClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, *a, **k):
            assert url.endswith("/audit")
            return _FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    resp = client.get("/api/activity").json()
    assert resp[0]["topic"] == "workflow.completed"


def test_agents_degrades_to_empty_list_when_registry_unreachable(monkeypatch):
    class _FakeAsyncClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, *a, **k):
            raise ConnectionError("registry down")

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
    assert client.get("/api/agents").json() == []
