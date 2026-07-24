import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_unconfigured_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "billing"
    assert body["stripe_configured"] is False


def test_checkout_fails_closed_without_key(monkeypatch):
    # No STRIPE_API_KEY -> must NOT attempt a charge; returns configured:false,
    # never a 5xx (and never a live Stripe call).
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    r = client.post("/billing/checkout", json={"product": "Pro", "amount_minor": 9900})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["checkout_url"] is None
    assert "STRIPE_API_KEY" in body["reason"]


def test_checkout_uses_stripe_when_key_present(monkeypatch):
    # With a (fake) key set, it calls Stripe and returns the hosted URL. httpx
    # is mocked so no network / no real charge; proves the request path + that
    # the key is used only as a Bearer header, never returned in the response.
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy_not_real")
    import app.main as m

    captured = {}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123"}

    def _fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return _FakeResp()

    monkeypatch.setattr(m.httpx, "post", _fake_post)
    r = client.post("/billing/checkout", json={"product": "Pro", "amount_minor": 9900, "currency": "gbp"})
    body = r.json()
    assert body["configured"] is True
    assert body["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_123"
    assert body["session_id"] == "cs_test_123"
    # key travels only in the Authorization header, and is not echoed back
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert "sk_test_dummy_not_real" not in r.text
    assert captured["data"]["line_items[0][price_data][unit_amount]"] == 9900


def test_config_endpoint(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    body = client.get("/billing/config").json()
    assert body["stripe_configured"] is False
    assert "payment" in body["modes"]


def test_no_live_key_committed_in_source():
    # Guard: a live Stripe key prefix must never appear in this service's code.
    # Needles are assembled at runtime so the literal prefixes never exist in
    # any source file (including this test), which would otherwise self-trip.
    needles = ["rk_" + "live_", "sk_" + "live_"]
    here = os.path.dirname(os.path.dirname(__file__))
    for root, _dirs, files in os.walk(here):
        if "__pycache__" in root:
            continue
        for fn in files:
            if fn.endswith((".py", ".txt", ".yml", ".yaml", ".env")):
                text = open(os.path.join(root, fn), encoding="utf-8", errors="ignore").read()
                for needle in needles:
                    assert needle not in text, f"live key leaked in {fn}"
