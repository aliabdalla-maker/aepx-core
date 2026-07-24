from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "aepx-console"


def test_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AEP-X" in resp.text and "Console" in resp.text


def test_bridge_endpoints_degrade_to_502_without_stack():
    # No live bus in the unit-test environment — every proxy must degrade to
    # a clean 502 with a reason, never a raw 500 (matches platform/workbench).
    read = client.post("/api/chain/read", json={
        "address": "0x0000000000000000000000000000000000000000",
        "abi": [], "function": "anchorCount"})
    assert read.status_code == 502
    assert "unreachable" in read.json()["detail"]
    assert client.post("/api/chain/write", json={
        "address": "0x0000000000000000000000000000000000000000",
        "abi": [], "function": "anchor", "args": ["0x00"]}).status_code == 502
    assert client.post("/api/oracle/decide", json={"prompt": "hi"}).status_code == 502
    assert client.post("/api/oracle/poll").status_code == 502


def test_chain_status_returns_snapshot_even_when_node_down():
    # The Blockchain overview must never 502 — it returns a snapshot with
    # node_up=false so the UI can show "degraded" rather than an error.
    resp = client.post("/api/chain/status", json={"connector": "ethereum"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["connector"] == "ethereum"
    assert body["node_up"] is False


def test_platform_wide_endpoints_degrade_to_502_without_stack():
    # The whole-platform surface, not just the bridge — each proxies a
    # different service and must degrade cleanly when it's unreachable.
    assert client.get("/api/connectors").status_code == 502
    assert client.get("/api/trust/some-agent").status_code == 502
    assert client.get("/api/agents").status_code == 502
    assert client.post("/api/memory", json={"agent_id": "a", "content": {}}).status_code == 502
    assert client.get("/api/discover?capability=x").status_code == 502
    assert client.post("/api/workflow", json={"name": "w", "steps": []}).status_code == 502
    assert client.get("/api/policy?risk_level=S1").status_code == 502
    assert client.get("/api/ledger/anchors").status_code == 502
    assert client.get("/api/models").status_code == 502
    assert client.get("/api/brain/status").status_code == 502
    assert client.post("/api/chat", json={"prompt": "hi"}).status_code == 502
    assert client.get("/api/billing/config").status_code == 502
    assert client.post("/api/billing/checkout", json={"product": "x", "amount_minor": 100}).status_code == 502


def test_health_map_never_blanks_when_targets_down():
    # health-map catches each target independently, so it returns 200 with
    # every service marked down rather than failing as a whole — and it now
    # covers the whole platform, not just the bridge.
    body = client.get("/api/health-map").json()
    for svc in ("oracle-bridge", "connector-bus", "governance", "memory", "workflow", "brain", "billing"):
        assert svc in body, f"{svc} missing from health map"
        assert body[svc]["up"] is False
