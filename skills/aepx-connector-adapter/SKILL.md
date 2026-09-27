---
name: aepx-connector-adapter
description: Add a new connector to the AEP-X catalogue or replace a stub connector with a real (specialized) adapter in aepx-core. Use when asked to add, implement, or upgrade a connector such as SMTP, Salesforce, Slack or a blockchain RPC.
---

# Add or upgrade an AEP-X connector

Architecture (SOA-Architecture.md §3.1): one FastAPI service per category under `connectors/<category>/`, one adapter per external system. Uncatalogued names are rejected; catalogued ones without a specialized adapter fall back to `StubAdapter`. The bus, trust and governance gating need no changes.

## 1. Catalogue entry — `connectors/catalogue.json`

Add (or edit) an object in `connectors`:

```json
{ "name": "smtp", "category": "messaging", "protocols": ["SMTP"],
  "ai_risk_class": "AIA-R1", "min_trust_score": 50, "maturity": "specialized" }
```

- `category` must be one of the 11 existing services: enterprise, productivity, devtools, aiplatform, data, messaging, industrial, cloud, government, education, blockchain.
- Risk class drives governance: industrial and government are AIA-R3 and policy-denied by default (`max_risk_level: S2`). Raising that is a governance decision — flag it to the user, don't change the policy yourself.
- Set `maturity` to `specialized` only once a real adapter exists; otherwise `stub`.

## 2. Adapter — `connectors/<category>/app/adapters.py`

Follow the existing shape: a class with `execute(self, payload: dict) -> dict`, dispatching on `payload["op"]`, returning `op`, `result`, `source: "connector:<name>"`, `confidence`, `maturity`. Return `{"op": op, "error": "..."}` for unsupported ops. Register it in `SPECIALIZED = {"<name>": <Adapter>()}`.

- Read credentials from environment variables; never hard-code them. Add each new variable to `.env.example` and to that category service's `environment:` in `docker-compose.yml`.
- Degrade cleanly when credentials are absent (clear error, not a crash) — the repo's convention is that everything runs with zero external config.
- Add any client library to `connectors/<category>/requirements.txt` with a pinned version.

## 3. Tests — `connectors/<category>/tests/`

Cover each op, the unsupported-op path and the missing-credentials path. Mock network calls. Run with the `aepx-test-component` skill.

## 4. Docs

Update `docs/Connector-Catalogue.md` (counts and the connector's row) and, if the number of real adapters changed, the "Built" section of `README.md`.

## 5. Try it end to end

With the stack up: `aepx invoke` from the CLI, or the governed invoke in the AEP-X Console (:8083). Check the call appears in the governance audit feed.
