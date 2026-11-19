---
name: aepx-svc-registry
description: AEP-X Registry service. It registers, fetches and lists agents in Postgres, ranked by trust_score, and mints a did:key via Identity fail-open, with an in-memory fallback. Use when working on, debugging, calling or extending the registry service, the agents table or schemas/openapi/registry.yaml in aepx-core.
---

# Registry service (`services/registry`)

## Role
The Agent Registry is the system of record for agents. It stores each agent's id, name, organisation, version, a trust-score snapshot and a DID. On registration it gives every agent a `did:key` if the caller did not supply one, which applies Law 1, Identity Before Interaction (RFC-0006). This is best-effort, so Identity being down never blocks registration.

## Where
- Code: `services/registry/app/main.py`. Contract: `schemas/openapi/registry.yaml`.
- Compose service: `registry`. Host port `8003` maps to container port `8000`.
- `depends_on: [postgres, identity]`. Compose sets `DATABASE_URL` and `IDENTITY_URL`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness and persistence check | `{status:"ok", service:"registry", persisted: bool}` |
| POST | `/agents` | Register an agent | Body `AgentIn {name: str, organisation_id?: str, did?: str}`. Returns `Agent {id, name, organisation_id, did, version="0.0.1", trust_score=0}`. |
| GET | `/agents/{agent_id}` | Fetch one agent | Returns `Agent`. Returns **404** if the agent is missing *or* the id is not a UUID (on the DB path), never 500. |
| GET | `/agents` | List all agents | `Agent[]` ordered by `trust_score DESC, name ASC` |

`registry.yaml` (OpenAPI 3.0.3, version 0.0.1) declares only the paths above, without schemas.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://aepx:aepx_dev_only@postgres:5432/aepx` | Postgres DSN (`connect_timeout=3`) |
| `IDENTITY_URL` | `http://identity:8000` | Target for `POST /did` when minting a DID (3s timeout) |

## Data & dependencies
- Postgres table `agents`:
  - `001_init.sql` creates `id UUID DEFAULT gen_random_uuid()`, `organisation_id UUID`, `name`, `version DEFAULT '0.0.1'`, `trust_score INT DEFAULT 0` and `created_at`.
  - `007_blockchain.sql` adds `did TEXT UNIQUE` (nullable).
- Degrade behaviour is fail-open. On a missing driver, a failed connection or a query error, POST and list fall back to the in-memory dict `_AGENTS`, which is lost on restart. The in-memory ids are `uuid4` strings.
- It calls Identity `POST {IDENTITY_URL}/did` when `did` is not supplied. Any failure leaves `did = None`.
- There is no Kafka.
- `trust_score` here is a creation-time snapshot. The live score lives in the Trust service, and `console/app/main.py` merges the two for its ranking.
- Callers:
  - `services/gateway` (`GET /agents/{id}` in `/execute`)
  - `services/workflow` (`GET /agents/{id}` per step)
  - `services/discovery` (`GET /agents`)
  - `console`, `platform/workbench`, `platform/aepx-console`
  - `sdk/python/aepx/agent.py` (`POST /agents` with `{name, did}`)

## Run & test
```bash
pip install -r services/registry/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/registry
cd services/registry && python -m pytest tests -v
```
The tests run without Postgres or Identity. They cover `persisted False`, create/get, the list order, a 404 for an unknown or malformed id, `did is None` when Identity is unreachable, and storing a supplied DID.

Run it alone:
```bash
cd services/registry && DATABASE_URL=postgresql://aepx:aepx_dev_only@localhost:5432/aepx \
  IDENTITY_URL=http://localhost:8001 uvicorn app.main:app --port 8003
curl -s -X POST http://localhost:8003/agents -H 'content-type: application/json' -d '{"name":"tutor-agent"}'
curl -s http://localhost:8003/agents
curl -s http://localhost:8003/agents/<id>
```

## Changing it
- Keep `schemas/openapi/registry.yaml` in sync when you add or change paths.
- The `Agent` shape (`id`, `name`, `trust_score`, `did`, `version`) is consumed by Gateway, Workflow, Discovery (it spreads the whole agent dict into results), the console and the SDK. Grep with `grep -rn "REGISTRY_URL\|registry_url\|/agents" services connector-bus sdk platform console`.
- A schema change needs a new numbered migration in `schemas/sql/`, never an edit to an old one. `docker-compose.yml` mounts that directory as the Postgres init scripts.
- The same SQL `SELECT` column list appears three times. Keep them aligned with the `Agent(...)` constructors.
- Never let `_mint_did` raise or block. `test_agent_creation_fails_open_when_identity_unreachable` guards this.
- The list ordering by trust is a documented contract, because the console's ranking relies on it.

## Related skills
- aepx-svc-identity (DID minting)
- aepx-svc-trust (the live scores)
- aepx-svc-gateway, aepx-svc-workflow, aepx-svc-discovery (its callers)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
