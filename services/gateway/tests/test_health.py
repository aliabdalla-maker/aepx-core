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
