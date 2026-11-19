---
name: aepx-conn-data
description: Data connector service (connectors/data) with 16 SQL, NoSQL, cache, vector-store, graph and search connectors (PostgreSQL, MongoDB, Redis, pgvector, Pinecone, Neo4j, Elasticsearch). Use when invoking or testing a data connector or building its first real adapter.
---

# Data connectors (`connectors/data`)

## Role

Databases, caches, vector stores, graph and search. AIA-R1 / min trust 50 for everything except the caches `redis` and `memcached` (AIA-R0 / 40). All are allowed by the default policy and reachable by a fresh agent (trust 50).

Risk classes in this category: AIA-R0 x2, AIA-R1 x14.

## Where

- Code: `connectors/data/app/main.py` (routes) and `connectors/data/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/data/tests/test_health.py`. Deps: `connectors/data/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-data`**, host port **8025** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "data")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-data:8000`, overridable with `CONNECTOR_URL_DATA` on the connector-bus.

## Connectors

16 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `postgresql` | SQL | AIA-R1 | 50 | stub |
| `mysql` | SQL | AIA-R1 | 50 | stub |
| `sqlserver` | SQL | AIA-R1 | 50 | stub |
| `oracle-db` | SQL | AIA-R1 | 50 | stub |
| `mongodb` | Wire | AIA-R1 | 50 | stub |
| `cassandra` | CQL | AIA-R1 | 50 | stub |
| `dynamodb` | REST | AIA-R1 | 50 | stub |
| `redis` | RESP | AIA-R0 | 40 | stub |
| `memcached` | Memcache | AIA-R0 | 40 | stub |
| `pgvector` | SQL | AIA-R1 | 50 | stub |
| `pinecone` | REST | AIA-R1 | 50 | stub |
| `weaviate` | REST, GraphQL | AIA-R1 | 50 | stub |
| `milvus` | gRPC | AIA-R1 | 50 | stub |
| `qdrant` | REST, gRPC | AIA-R1 | 50 | stub |
| `neo4j` | Bolt | AIA-R1 | 50 | stub |
| `elasticsearch` | REST | AIA-R1 | 50 | stub |

## Specialized adapters

All 16 connectors are stubs: `SPECIALIZED = {}` in `connectors/data/app/adapters.py` (it imports nothing beyond the stub class). `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-data", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `data`, otherwise 404 `connector '<name>' is not registered in category 'data'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/data/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/data
cd connectors/data && python -m pytest tests -v
```

Tests: health, 16 catalogue entries, stub dispatch (`elasticsearch`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8025/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/pinecone","payload":{"op":"query"}}'
```

Returns the canonical stub (`maturity: "stub"`). The bus test `test_route_stub_connector_from_catalogue` uses this connector.

## Adding a real adapter here

- This is the first specialized adapter for the category. Add `import os` / `import httpx` (or a pinned driver in `connectors/data/requirements.txt`) and register the class in `SPECIALIZED`.
- Read the connection string/credentials from env and degrade to `specialized_degraded` when absent or unreachable. Add a compose `environment:` block for `connector-data`, since none exists.
- Update `catalogue.json` `maturity` to `specialized` and regenerate docs/Connector-Catalogue.md.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
