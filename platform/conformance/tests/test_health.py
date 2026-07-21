from fastapi.testclient import TestClient
from app.main import app, _RUNS

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "conformance"
    assert body["checks_available"] > 0


def test_checks_catalogue():
    checks = client.get("/checks").json()
    ids = [c["id"] for c in checks]
    assert "core.envelope-shape" in ids
    assert "did.roundtrip" in ids
    assert all({"id", "rfc", "title"} <= set(c) for c in checks)


def test_run_against_unreachable_target_skips_never_500s():
    # No live deployment in the unit-test environment — network checks must
    # SKIP (degrade-don't-fail), the offline envelope-shape check passes,
    # and the endpoint returns a well-formed report, never an error.
    resp = client.post("/runs", json={
        "target": {"bus_url": "http://localhost:1", "identity_url": "http://localhost:1",
                    "trust_url": "http://localhost:1", "governance_url": "http://localhost:1",
                    "gateway_url": "http://localhost:1", "registry_url": "http://localhost:1"}})
    assert resp.status_code == 200
    run = resp.json()
    assert run["failed"] == 0
    assert run["skipped"] > 0
    assert any(r["id"] == "core.envelope-shape" and r["status"] == "pass" for r in run["results"])


def test_runs_are_kept_and_retrievable():
    before = len(_RUNS)
    run = client.post("/runs", json={
        "checks": ["core.envelope-shape"],
        "target": {"bus_url": "http://localhost:1"}}).json()
    assert len(_RUNS) == before + 1
    fetched = client.get(f"/runs/{run['run_id']}").json()
    assert fetched == run
    listing = client.get("/runs").json()
    assert listing[0]["run_id"] == run["run_id"]


def test_unknown_run_404():
    assert client.get("/runs/999999").status_code == 404
