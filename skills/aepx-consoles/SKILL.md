---
name: aepx-consoles
description: The four AEP-X web GUIs — console (:8080 LLM box), platform/workbench (:8081), platform/conformance (:8082), platform/aepx-console (:8083). Covers what each does, backend calls, env vars, run/test, and adding a panel or route. Use when changing or debugging any of the GUIs.
---

# AEP-X consoles and platform GUIs

Each GUI is a FastAPI backend plus a single static `static/index.html`, with no frontend build step. The browser only calls the app's own `/api/...` (or `/runs`) routes. The backend proxies to in-cluster services, because a browser cannot resolve docker-internal hostnames. Every container listens on port 8000.

| App | Host port | Build context | Backend calls |
|---|---|---|---|
| `console/` (LLM box) | 8080 | `./console` | raw `httpx` to bus, registry, trust, governance |
| `platform/workbench` | 8081 | repo root (installs `sdk/python`) | `AepxClient` plugins |
| `platform/conformance` | 8082 | repo root (installs `sdk/python`) | `aepx.conformance.run_conformance` |
| `platform/aepx-console` | 8083 | repo root (installs `sdk/python`) | SDK plugins plus direct REST (20 entries in `SVC`) |

The three `platform/*` Dockerfiles `COPY sdk/python /sdk` and `pip install /sdk`. That is why compose builds them with `context: .` and `dockerfile: platform/<x>/Dockerfile`, and why a change to the SDK requires rebuilding them.

## console (:8080) — the LLM / machine-learning box

`console/app/main.py`. Env vars: `CONNECTOR_BUS_URL`, `REGISTRY_URL`, `TRUST_URL`, `GOVERNANCE_URL`, `UPLOAD_DIR` (default `/data/uploads`, the `console-uploads` volume) and `STATIC_DIR` (default `static`).

- `POST /api/chat` takes `{prompt, attachment_ids, connector="ml"}`. It builds an RFC-0001 envelope with `payload.op="completion"`, sender `aepx://agent/console`, and routes it via `{bus}/bus/route`. It returns `reply`, `model`, `confidence`, `maturity` (the adapter's per-call maturity wins over the catalogue's), `connector` and `trust_score_at_call_time`. A bus that cannot be reached returns 502. A denial passes through the bus status code.
- `POST /api/upload`, `GET /api/uploads`, `GET /api/uploads/{id}/content`: upload metadata lives in an in-memory dict.
- `GET /api/agents` returns the registry agents enriched with live Trust scores and sorted by score. It returns `[]` if Registry cannot be reached.
- `GET /api/activity` proxies Governance `/audit`.
- Static files are mounted at `/` last, so `/api` and `/health` take precedence.

## workbench (:8081) — utilisation platform (RFC-0007)

Env vars: `GATEWAY_URL`, `IDENTITY_URL`, `TRUST_URL`, `REGISTRY_URL`, `GOVERNANCE_URL`, `CONNECTOR_BUS_URL`, all passed into one `AepxClient`. Routes: `/api/connectors`, `POST /api/invoke` (default sender `aepx://agent/workbench`), `POST /api/did`, `GET /api/did/{did:path}`, `/api/trust/{id}`, `/api/ledger/anchors`, `/api/ledger/verify/{id}`, `/api/audit`, `GET`/`POST /api/agents`. Every call is wrapped in `_proxied()`: `ValueError` becomes 400, any other exception becomes a **502** with the reason, and nothing surfaces as a raw 500.

## conformance (:8082) — testing platform

Uses the same six env vars as the workbench, as `DEFAULT_TARGET`. Routes:
- `GET /checks`: the catalogue.
- `POST /runs`: body `{target?: {gateway_url, ...}, checks?: [ids]}`. Runs the suite with `timeout=15.0`.
- `GET /runs` and `GET /runs/{id}`: an in-memory ring buffer of the last 50 runs. An unknown ID returns 404.

## aepx-console (:8083) — one GUI over the whole platform

`platform/aepx-console/app/main.py`. It reads the full env block from `docker-compose.yml`: the six SDK URLs, plus `MEMORY_URL`, `CACHE_URL`, `DISCOVERY_URL`, `WORKFLOW_URL`, `SAFETY_URL`, `KNOWLEDGE_URL`, `VERIFICATION_URL`, `COST_OPTIMISER_URL`, `ML_INTEGRATION_URL`, `BRAIN_URL`, `MARKETPLACE_URL`, `BILLING_URL`, `ORACLE_BRIDGE_URL` (re-attaches `OraclePlugin`) and `CONNECTOR_URL_BLOCKCHAIN`.

- `SVC` is the single name → URL map. It drives both the Overview health grid (`/api/health-map` probes every entry concurrently with a 2s timeout and catches each one independently) and the `_svc_get` / `_svc_post` direct-REST helpers.
- `_proxied()` gives the same 400/502 discipline as the workbench.
- UI sections are declared in `static/index.html` as `<div class="nav" data-sec="X">` entries, each paired with a `<section id="sec-X" class="section">` block: overview, connectors, trust, flows, bridge (Blockchain), governance, billing, intelligence, chat. The page calls the backend through an `api(path, opts)` helper built on `fetch`.
- The chain and oracle routes are `/api/chain/read|write|rpc|status` and `/api/oracle/decide|poll|history`. `/api/chat` invokes the `ml` connector through the SDK.

## Run and test

```bash
docker compose up --build -d console workbench conformance aepx-console
pip install -r platform/aepx-console/requirements.txt pytest httpx2
pip install -e sdk/python                  # required for platform/* only
cd platform/aepx-console && python -m pytest tests -v
```

All four apps are in CI's `test-soa` matrix (`console`, `platform/conformance`, `platform/workbench`, `platform/aepx-console`). The tests run with no stack up and assert the degrade behaviour: 502 rather than 500, the health map never blanks, and a conformance run against an unreachable target SKIPs.

## Adding a route or panel (aepx-console)

1. Backend: add a pydantic request model if needed, then an `@app.get`/`@app.post("/api/...")` route. Return `_proxied(client.<plugin>.<fn>, ...)` for SDK-covered calls, or `_svc_get("<svc>", "/path")` / `_svc_post(...)` for direct REST. If the service is new, add it to `SVC` so it appears in the health grid, and add its `*_URL` env var to the `aepx-console` block in `docker-compose.yml`.
2. Frontend: add a `nav` div and a matching `section` in `static/index.html`, and wire buttons to `api("/api/...")`. Keep the offline or degraded rendering path (`showJSON` / `offline`).
3. Test: extend `tests/test_health.py` to assert the new route degrades to 502 when there is no stack.
4. Rebuild with `docker compose up --build -d aepx-console`.

For workbench and conformance, follow the same `_proxied` pattern. For `console/`, follow its raw-httpx pattern and keep the static mount last.

## Related skills

- `aepx-sdk` — the plugins the platform apps proxy through
- `aepx-rfcs-conformance` — what the conformance platform runs
- `aepx-blockchain` — the Blockchain section's chain and oracle backends
- `aepx-run-stack` — bringing the GUIs up
- `aepx-test-component` — CI-equivalent test runs
