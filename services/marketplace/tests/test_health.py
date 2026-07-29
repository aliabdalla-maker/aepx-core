from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "marketplace"


def test_create_and_get_listing():
    r = client.post("/marketplace/listings", json={"name": "Tutor Agent", "asset_type": "agent"})
    assert r.status_code == 200
    listing = r.json()
    assert listing["status"] == "draft"
    got = client.get(f"/marketplace/listings/{listing['id']}").json()
    assert got["name"] == "Tutor Agent"


def test_bad_asset_type_rejected():
    r = client.post("/marketplace/listings", json={"name": "x", "asset_type": "spaceship"})
    assert r.status_code == 400


def test_publish_fails_closed_without_trust_or_governance():
    # No Trust/Governance reachable in the unit env -> the gate must NOT
    # publish; it fails closed with a reason (Law 2: no trust check, no publish).
    lid = client.post("/marketplace/listings", json={"name": "x"}).json()["id"]
    out = client.post(f"/marketplace/listings/{lid}/publish").json()
    assert out["published"] is False
    assert "fail-closed" in out["reason"]
    assert client.get(f"/marketplace/listings/{lid}").json()["status"] != "published"


def test_publish_gate_denies_low_trust(monkeypatch):
    # Trust reachable but below the bar -> denied even though policy would allow.
    import app.main as m

    monkeypatch.setattr(m, "_check_trust", lambda e: (10, None))
    monkeypatch.setattr(m, "_check_policy", lambda r: (True, None))
    lid = client.post("/marketplace/listings", json={"name": "low-trust"}).json()["id"]
    out = client.post(f"/marketplace/listings/{lid}/publish").json()
    assert out["published"] is False
    assert "trust 10" in out["reason"]


def test_publish_gate_allows_when_trust_and_policy_pass(monkeypatch):
    import app.main as m

    monkeypatch.setattr(m, "_check_trust", lambda e: (85, None))
    monkeypatch.setattr(m, "_check_policy", lambda r: (True, None))
    lid = client.post("/marketplace/listings", json={"name": "ok"}).json()["id"]
    out = client.post(f"/marketplace/listings/{lid}/publish").json()
    assert out["status"] == "published"
    assert out["publish_trust_score"] == 85


def test_publish_gate_denies_when_policy_blocks(monkeypatch):
    import app.main as m

    monkeypatch.setattr(m, "_check_trust", lambda e: (85, None))
    monkeypatch.setattr(m, "_check_policy", lambda r: (False, "over ceiling"))
    lid = client.post("/marketplace/listings", json={"name": "risky", "risk_level": "S4"}).json()["id"]
    out = client.post(f"/marketplace/listings/{lid}/publish").json()
    assert out["published"] is False
    assert "policy denied" in out["reason"]
