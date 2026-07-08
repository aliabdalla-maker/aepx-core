import fakeredis
from fastapi.testclient import TestClient
import app.main as main

main.r = fakeredis.FakeRedis(decode_responses=True)
client = TestClient(main.app)


def test_health():
    resp = client.get("/health")
    assert resp.json()["status"] == "ok"


def test_l1_roundtrip():
    client.post("/cache/L1/foo", json={"answer": 42})
    resp = client.get("/cache/L1/foo")
    assert resp.json() == {"layer": "L1", "key": "foo", "value": {"answer": 42}, "hit": True}


def test_l5_denied_without_policy_flag():
    resp = client.post("/cache/L5/bar", json={"answer": 1})
    assert resp.status_code == 403


def test_legacy_single_layer_alias():
    client.post("/cache/legacy-key", json={"x": 1})
    resp = client.get("/cache/legacy-key")
    assert resp.json()["value"] == {"x": 1}
