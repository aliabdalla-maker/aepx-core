"""AEP-X Billing — Stripe payment processing.

Creates Stripe-hosted Checkout Sessions so the platform can charge for the
things the Monetization Strategy describes (subscriptions, marketplace fees,
certification exams, usage). Two deliberate safety choices:

  * **The secret key never lives in the repo.** It is read once from the
    STRIPE_API_KEY environment variable at call time and used only as a
    Bearer token to api.stripe.com. It is never logged, returned, or
    persisted. Supply it via a secrets manager / deployment env, not git.
  * **Card data never touches AEP-X.** We create a Checkout Session and hand
    back Stripe's hosted URL; the customer enters payment details on Stripe's
    page. This is the PCI-safe pattern and also honours the platform's own
    Law 6 (human approval for financial decisions) — a human completes the
    payment on Stripe, the platform never moves funds autonomously.

Degrade-clean like everything else: with STRIPE_API_KEY unset (the default,
and what CI runs with), the endpoints return a well-formed
``configured: false`` response, never a 5xx and never a live charge.
"""
import os

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AEP-X Billing", version="0.1.0")

STRIPE_API_BASE = os.getenv("STRIPE_API_BASE", "https://api.stripe.com/v1")


def _stripe_key() -> str | None:
    # Read at call time (not import) so rotating the secret doesn't need a
    # rebuild, and so the value is never captured in module state/logs.
    return os.getenv("STRIPE_API_KEY")


def _configured() -> bool:
    return bool(_stripe_key())


class CheckoutIn(BaseModel):
    product: str = "AEP-X Professional"
    amount_minor: int = 9900          # smallest currency unit (pence) — e.g. £99.00
    currency: str = "gbp"
    quantity: int = 1
    mode: str = "payment"             # "payment" (one-off) or "subscription"
    success_url: str = "https://example.com/success"
    cancel_url: str = "https://example.com/cancel"


@app.get("/health")
def health():
    # Never leaks the key — only whether one is present.
    return {"status": "ok", "service": "billing", "stripe_configured": _configured()}


@app.get("/billing/config")
def config():
    return {
        "stripe_configured": _configured(),
        "modes": ["payment", "subscription"],
        "note": "card entry is on Stripe-hosted Checkout; AEP-X never handles card data",
    }


@app.post("/billing/checkout")
def create_checkout(body: CheckoutIn):
    """Create a Stripe Checkout Session and return its hosted URL. Fails
    closed (configured:false) when no key is set — never attempts a live
    charge without one."""
    key = _stripe_key()
    if not key:
        return {
            "configured": False,
            "reason": "STRIPE_API_KEY unset — set it as a deployment secret to enable payments",
            "checkout_url": None,
        }
    # Stripe expects form-encoded params with its bracket syntax for nesting.
    form = {
        "mode": body.mode,
        "success_url": body.success_url,
        "cancel_url": body.cancel_url,
        "line_items[0][quantity]": body.quantity,
        "line_items[0][price_data][currency]": body.currency,
        "line_items[0][price_data][product_data][name]": body.product,
        "line_items[0][price_data][unit_amount]": body.amount_minor,
    }
    if body.mode == "subscription":
        form["line_items[0][price_data][recurring][interval]"] = "month"
    try:
        resp = httpx.post(
            f"{STRIPE_API_BASE}/checkout/sessions",
            data=form,
            headers={"Authorization": f"Bearer {key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        session = resp.json()
        return {
            "configured": True,
            "checkout_url": session.get("url"),
            "session_id": session.get("id"),
            "amount_minor": body.amount_minor,
            "currency": body.currency,
        }
    except Exception as e:
        # Surface a clean reason; never echo the key or raw auth error detail.
        return {
            "configured": True,
            "checkout_url": None,
            "reason": f"stripe_request_failed ({type(e).__name__})",
        }
