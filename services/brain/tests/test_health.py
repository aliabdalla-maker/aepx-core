import time

from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "brain"
    assert body["persisted"] is False  # no Postgres in the unit-test environment
    assert body["monitoring"] == len(main.MONITORED_SERVICES)


def test_brain_status_shape():
    body = client.get("/brain/status").json()
    assert set(body["services"]) == set(main.MONITORED_SERVICES)


def test_circuit_status_default_closed_for_unknown_connector():
    resp = client.get("/brain/circuit/never-seen-connector").json()
    assert resp["state"] == "closed"
    assert resp["allowed"] is True


def test_record_incident_falls_back_to_memory_without_postgres():
    main._incidents_fallback.clear()
    main._record_incident("service_down", "test-target", "3 consecutive failed health checks")
    body = client.get("/brain/incidents").json()
    assert body[0]["kind"] == "service_down"
    assert body[0]["target"] == "test-target"


def test_circuit_opens_after_failure_threshold(monkeypatch):
    main._circuit_fallback.clear()

    class _FakeResp:
        def json(self):
            # Governance returns newest-first; 5 consecutive denials for 'flaky-connector'
            return [
                {"topic": "connector.failed", "event": {"connector": "flaky-connector", "outcome": "denied"}}
                for _ in range(main.CIRCUIT_FAILURE_THRESHOLD)
            ]

    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: _FakeResp())
    main._recompute_reliability_and_circuits()

    status = client.get("/brain/circuit/flaky-connector").json()
    assert status["state"] == "open"
    assert status["allowed"] is False
    assert status["reliability_score"] == 0.0


def test_circuit_stays_closed_for_healthy_connector(monkeypatch):
    main._circuit_fallback.clear()

    class _FakeResp:
        def json(self):
            return [{"topic": "connector.invoked", "event": {"connector": "reliable-connector", "outcome": "invoked"}}] * 10

    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: _FakeResp())
    main._recompute_reliability_and_circuits()

    status = client.get("/brain/circuit/reliable-connector").json()
    assert status["state"] == "closed"
    assert status["allowed"] is True
    assert status["reliability_score"] == 1.0


def test_circuit_transitions_open_to_half_open_after_cooldown(monkeypatch):
    main._circuit_fallback.clear()
    # seed an OPEN circuit whose cooldown has already elapsed
    main._circuit_fallback["cooling-down-connector"] = {
        "state": "open", "consecutive_failures": main.CIRCUIT_FAILURE_THRESHOLD,
        "reliability_score": 0.0, "opened_at": time.time() - main.CIRCUIT_COOLDOWN_SECONDS - 1,
    }

    class _FakeResp:
        def json(self):
            return [{"topic": "connector.failed", "event": {"connector": "cooling-down-connector", "outcome": "denied"}}]

    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: _FakeResp())
    main._recompute_reliability_and_circuits()

    status = client.get("/brain/circuit/cooling-down-connector").json()
    assert status["state"] == "half_open"


def test_reliability_endpoint_lists_connectors(monkeypatch):
    main._circuit_fallback.clear()
    main._circuit_fallback["some-connector"] = {
        "state": "closed", "consecutive_failures": 0, "reliability_score": 0.9, "opened_at": None,
    }
    body = client.get("/brain/reliability").json()
    assert any(c["connector"] == "some-connector" for c in body)
