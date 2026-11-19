---
name: aepx-svc-billing
description: Billing service for AEP-X. It creates Stripe-hosted Checkout Sessions, reads STRIPE_API_KEY from the environment only, and never handles card data. Use when working on, debugging, calling or extending the billing service in aepx-core, or when checkout returns configured:false.
---

# Billing service (`services/billing`)

## Role
This service creates Stripe-hosted Checkout Sessions so the platform can charge for what the Monetization Strategy describes: subscriptions, marketplace fees, certification exams and usage. It has two invariants:
1. **The secret key never lives in the repo.** It is read from `STRIPE_API_KEY` at call time and sent only as a Bearer header to Stripe. It is never logged, returned or persisted.
2. **Card data never touches AEP-X.** The customer pays on Stripe's hosted page. The docstring and docs/Console-and-Bridge.md §3 say this also honours Law 6 (Human Authority): a human completes the payment, and the platform never moves funds on its own.

## Where
- Code: `services/billing/app/main.py`. Docs: `docs/Console-and-Bridge.md` §3.
- Compose service `billing`, host port **8017** -> container 8000.
- Environment `STRIPE_API_KEY=${STRIPE_API_KEY:-}`, which is empty by default.
- It has no `depends_on`. It talks only to Stripe.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"billing", stripe_configured: bool}`. The key is never included |
| GET | `/billing/config` | Configuration state | `{stripe_configured, modes:["payment","subscription"], note}` |
| POST | `/billing/checkout` | Create a Checkout Session | See below |

`POST /billing/checkout` request, `CheckoutIn`:
- `product="AEP-X Professional"`
- `amount_minor=9900`, in the smallest currency unit
- `currency="gbp"`
- `quantity=1`
- `mode="payment"`. `"subscription"` adds a monthly recurring interval.
- `success_url`, `cancel_url`, which default to `example.com` placeholders

Responses:
| Case | Response |
|---|---|
| No key set | `{configured:false, reason, checkout_url:null}` |
| Success | `{configured:true, checkout_url, session_id, amount_minor, currency}` |
| Stripe error | `{configured:true, checkout_url:null, reason:"stripe_request_failed (<ExceptionType>)"}` |

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `STRIPE_API_KEY` | unset | Stripe secret key, **from the environment only**, read on every call, so rotating it needs no rebuild. Set it in a git-ignored `.env`, starting from the empty entry in `.env.example`, or as a deployment secret. Never put a real key in code, tests, docs, skills or commits |
| `STRIPE_API_BASE` | `https://api.stripe.com/v1` | Stripe API base URL. It can be pointed at a mock for testing |

## Data & dependencies
- **Storage:** none. The service is stateless and persists no session records.
- **Outbound:** `POST {STRIPE_API_BASE}/checkout/sessions`, form-encoded with Stripe's bracket syntax (`line_items[0][price_data][unit_amount]`, and so on), with a 15 s timeout. The key goes only in the `Authorization: Bearer` header.
- **Other AEP-X services:** none. It uses no Kafka and no Postgres.
- **Fail-closed when unconfigured:** with no key it returns `configured:false`. It never returns a 5xx and never makes a live call. Stripe errors are caught, and the response names only the exception type, never the key or raw auth detail.
- **Callers:** `platform/aepx-console` proxies `/api/billing/config` → `/billing/config` (it never proxies the key) and `/api/billing/checkout` → `/billing/checkout`, passing `CheckoutRequest.model_dump()`. The Gateway polls its `/health` (`BILLING_URL`), so it is covered by the `gateway.health` conformance check. It is not in the Brain's `MONITORED_SERVICES`.

## Run & test
```bash
pip install -r services/billing/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/billing
cd services/billing && python -m pytest tests -v
```
The tests:
- delete `STRIPE_API_KEY` to exercise the fail-closed path
- monkeypatch `httpx.post` with a dummy key to exercise the Stripe path without any network call
- walk the service directory to make sure no live-key prefix appears in any `.py/.txt/.yml/.yaml/.env` file

Run on its own. With no key set, checkout safely returns `configured:false`:
```bash
cd services/billing && uvicorn app.main:app --port 8017
curl -s localhost:8017/health
curl -s localhost:8017/billing/config
curl -s -X POST localhost:8017/billing/checkout -H 'Content-Type: application/json' \
  -d '{"product":"AEP-X Professional","amount_minor":9900,"currency":"gbp"}'
```
To exercise the real path, export `STRIPE_API_KEY` in your shell from your own Stripe **test-mode** key before starting uvicorn. Don't write it into any file tracked by git.

## Changing it
- Keep reading the key through `_stripe_key()` at call time. Never cache it in module state, log it, echo it in a response, or include it in exception text.
- Never add a real or live-looking key, even as a test fixture. The source guard test fails on live prefixes, and the existing test builds its dummy value at runtime. If you add a new file type to the service, extend the guard's extension list.
- Keep the unconfigured path free of 5xx errors and network calls. The `configured`, `checkout_url` and `reason` keys are what the aepx-console Billing panel displays.
- Subscription mode hard-codes `recurring[interval]=month`. If you add other intervals, add a field to `CheckoutIn` and to the console's `CheckoutRequest`.
- Card handling must stay on Stripe's hosted page. Don't add endpoints that accept card numbers.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "BILLING_URL\|/billing/" services connector-bus sdk platform console`.

## Related skills
- aepx-run-stack: set `STRIPE_API_KEY` in a git-ignored `.env`
- aepx-test-component, aepx-ci-debug
- aepx-svc-marketplace: marketplace fees are a billing use case
