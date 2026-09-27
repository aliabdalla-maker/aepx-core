---
name: aepx-connector-adapter
description: Add a new connector to the AEP-X catalogue or replace a stub connector with a real (specialized) adapter in aepx-core, end to end — catalogue, adapter, credentials, tests, docs, governed invoke. Use when asked to add, implement, or upgrade a connector such as SMTP, Salesforce, Slack or a blockchain RPC.
---

# Add or upgrade an AEP-X connector

Architecture (SOA-Architecture.md §3.1): one FastAPI service per category under `connectors/<category>/`, one adapter per external system. The bus (`aepx-connector-bus`) looks the name up in `connectors/catalogue.json`, checks trust ≥ `min_trust_score` (Law 2) and governance policy on `ai_risk_class`, then forwards to the category service. Catalogued names without a specialized adapter fall back to `StubAdapter`. You don't need to change the bus, trust or governance.

Each category's current connectors and adapters are in `aepx-conn-<category>`.

## 1. Catalogue entry — `connectors/catalogue.json`

Add (or edit) an object in `connectors`:

```json
{ "name": "smtp", "category": "messaging", "protocols": ["SMTP"],
  "ai_risk_class": "AIA-R1", "min_trust_score": 50, "maturity": "specialized" }
```

- `category` must be one of the 11 existing services: enterprise, productivity, devtools, aiplatform, data, messaging, industrial, cloud, government, education, blockchain.
- Risk class drives governance. All of industrial and most of government is AIA-R3, which the seed policy (`max_risk_level: S2`) denies. Raising that is a governance decision (`aepx-governance-policy`). Flag it to the user; don't change the policy yourself.
- `min_trust_score`: new senders start at trust 50. A connector at 60 or 70 returns 403 for fresh agents until their trust rises. Choose deliberately, and say so in the tests and docs.
- Set `maturity` to `specialized` only once a real adapter exists; otherwise use `stub`.

## 2. Adapter — `connectors/<category>/app/adapters.py`

Follow the existing shape. Write a class with `execute(self, payload: dict) -> dict` that dispatches on `payload["op"]` and returns `op`, `result`, `source: "connector:<name>"`, `confidence` and `maturity`. For unsupported ops, return `{"op": op, "error": "..."}`. Register it in `SPECIALIZED = {"<name>": <Adapter>()}`.

Good references:

- `devtools` (GitHub/GitLab/Docker Hub, which make real HTTP calls).
- `blockchain` (ethereum `contract_read`/`contract_write`).
- `aiplatform` (the `ml` connector backed by Ollama).

`SalesforceAdapter` is marked specialized but returns a hard-coded contact, so don't copy it as a model of a live integration.

- Read credentials from environment variables; never hard-code them. Add each new variable to:
  - `.env.example`, with an empty or placeholder value
  - that category service's `environment:` in `docker-compose.yml` (e.g. `- SMTP_HOST=${SMTP_HOST:-}`)

  Several existing adapters skip this, reading `SLACK_BOT_TOKEN`, `GITHUB_TOKEN`, `GITLAB_TOKEN` and `EVM_PRIVATE_KEY` without either. Don't repeat that.
- Degrade cleanly when credentials are absent: return a clear error, don't crash. The repo's convention is that everything runs with zero external config.
- Add any client library to `connectors/<category>/requirements.txt` with a pinned version.
- Return errors in the body rather than raising. The bus doesn't inspect the category service's HTTP status, so a 4xx/5xx from your service would still be recorded as `invoked`.

## 3. Tests — `connectors/<category>/tests/`

Cover each op, the unsupported-op path and the missing-credentials path. Mock network calls so tests need no credentials or network. Run them with `aepx-test-component`.

## 4. Docs and generated artefacts

- Regenerate `docs/Connector-Catalogue.md` with `python scripts/gen_connector_catalogue.py`. Never hand-edit it; CI's `catalogue` job fails if it's stale.
- Update `schemas/sql/003_connectors.sql` if the connector should be seeded. It says it's generated from `catalogue.json`, but no generator exists for it, so edit it by hand to match and tell the user.
- If the number of real adapters changed, update the "Built" section of `README.md`.

## 5. Try it end to end

With the stack up (`aepx-run-stack`):

```bash
aepx invoke <name> --payload '{"op":"<op>"}'      # see aepx-cli for how to run the CLI
```

You can also use the governed invoke in the AEP-X Console (:8083). Check that the call appears in the governance audit feed (`GET :8009/audit`, which needs Kafka up). Denials appear as `connector.failed` events.

## Related skills

- aepx-connector-bus, aepx-conn-<category>
- aepx-governance-policy, aepx-test-component
- aepx-cli, aepx-sdk
