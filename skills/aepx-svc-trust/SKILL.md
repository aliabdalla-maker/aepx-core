---
name: aepx-svc-trust
description: AEP-X Trust service. It computes the RFC-0002 five-component 0-100 trust score and level per entity, with fetch-or-create and an adjust endpoint, and falls back to memory when Postgres is down. Use when working on, debugging, calling or extending the trust service or trust scores in aepx-core.
---

# Trust service (`services/trust`)

## Role
Trust owns every entity's trust score. The score has five components (identity, behaviour, security, evidence and reputation), and their average gives a single 0-100 `trust_score` and an RFC-0002 `level`. The Connector Bus checks this score before every connector call, which enforces Law 2, Trust Before Execution (`connector-bus/app/main.py`). The Bus then nudges `behaviour` up after each successful call.

## Where
- Code: `services/trust/app/main.py`.
- Compose service: `trust`. Host port `8002` maps to container port `8000`.
- `depends_on: [postgres]`. Compose sets `DATABASE_URL`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness and persistence check | `{status:"ok", service:"trust", persisted: bool}`. `persisted` is true only if a Postgres connection succeeds. |
| GET | `/trust/{entity_id}` | Fetch-or-create a score | Query `entity_type` (default `agent`), used only when the row is inserted. Returns `{entity_id, trust_score, level, identity_score, behaviour_score, security_score, evidence_score, reputation_score}`. An unknown entity gets every component at 50, never a 404. |
| POST | `/trust/{entity_id}/adjust` | Nudge one component | Body `AdjustIn {component: str, delta: int}`. `component` may omit the `_score` suffix (`"behaviour"`). The new value is clamped to 0-100. Returns the same shape as GET. An unknown component returns `{"error": "unknown component '...'"}` with **HTTP 200**, not 4xx. |

Scoring: `trust_score = round(mean of the 5 components)`. The levels are:
- `>=90` Trusted
- `>=60` Verified
- `>=30` Provisional
- otherwise Untrusted

There is no OpenAPI contract for trust under `schemas/openapi/`.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://aepx:aepx_dev_only@postgres:5432/aepx` | Postgres DSN. The connection uses `connect_timeout=3`. |

## Data & dependencies
- Postgres table `trust_scores` (`schemas/sql/001_init.sql`):
  - Columns: `entity_id`, `entity_type`, five `*_score` INT columns, `updated_at`.
  - `entity_id` was widened from UUID to TEXT in `005_trust_entity_id_text.sql`, because wire senders such as `aepx://agent/console` are not UUIDs.
  - The SQL column defaults are 0. The service inserts 50 explicitly.
- Adjust uses `SELECT ... FOR UPDATE`, then `UPDATE ... SET <component> = %s, updated_at = now()`.
- Degrade behaviour is fail-open to an in-memory store. If psycopg is missing, the connection fails, or **any query errors**, the service uses the process-local dict `_FALLBACK`. Those scores do not survive a restart and are not shared across replicas.
- It calls no services and uses no Kafka.
- Callers:
  - `connector-bus` (GET, then `POST .../adjust` with `{"component":"behaviour","delta":1}`)
  - `services/discovery`
  - `services/cost-optimiser` (`/route/decide`)
  - `services/marketplace` (publish gate)
  - `console` (ranked agents)
  - `platform/*`
  - `sdk/python/aepx/plugins/trust.py`

## Run & test
```bash
pip install -r services/trust/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/trust
cd services/trust && python -m pytest tests -v
```
The tests assume no Postgres (`persisted is False`) and exercise the in-memory fallback: default 50/Provisional, adjust-and-refetch, clamp at 100, and an unknown component.

Run it alone (without a DB it just runs in fallback mode):
```bash
docker compose up -d postgres   # optional, for persistence
cd services/trust && DATABASE_URL=postgresql://aepx:aepx_dev_only@localhost:5432/aepx uvicorn app.main:app --port 8002
curl -s http://localhost:8002/trust/agent-1
curl -s -X POST http://localhost:8002/trust/agent-1/adjust -H 'content-type: application/json' -d '{"component":"behaviour","delta":10}'
```

## Changing it
- The response fields `trust_score`, `level` and the five `*_score` keys are read by the Bus (`trust_score` against `min_trust_score`), Discovery, Cost Optimiser, Marketplace (`>= 60` gate) and the console. Find them with `grep -rn "TRUST_URL\|trust_url\|/trust/" services connector-bus sdk platform console`.
- GET must never 500 or 404. A failure here would block every Bus call for every agent. Keep the broad `except` fallback, which ruff S110 is deliberately not selected to flag (`ruff.toml`).
- If you add a component, update `_COMPONENTS`, the SQL schema (as a new migration in `schemas/sql/`), the console's component list (`console/app/main.py`) and the tests.
- If you change the level thresholds, the test comment and the Marketplace/Bus trust thresholds interact with them. RFC-0002 is the spec.
- `entity_id` is free text, so do not re-add UUID validation.

## Related skills
- aepx-svc-discovery (ranks agents by trust)
- aepx-svc-registry (its `agents.trust_score` is a stale snapshot, and the console merges in Trust's live value)
- aepx-svc-gateway, aepx-svc-safety (a compose `depends_on` only)
- aepx-svc-cost-optimiser (reads trust in `/route/decide`)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
