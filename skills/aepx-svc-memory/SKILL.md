---
name: aepx-svc-memory
description: "AEP-X Memory service. It is a minimal in-process per-agent session memory: append entries and read them back. Use when working on, debugging, calling or extending the memory service or session memory in aepx-core."
---

# Memory service (`services/memory`)

## Role
Memory stores per-agent session memory. Each write appends a JSON object, stamped with a timestamp, to that agent's list, and a read returns the list. `docs/Microservices-Architecture-v2.md` describes it as covering only session memory (Instructional Manual §3.5). Semantic and knowledge retrieval is the separate Knowledge service.

## Where
- Code: `services/memory/app/main.py` (version `0.0.1`).
- Compose service: `memory`. Host port `8004` maps to container port `8000`.
- `depends_on: [postgres, redis]` in `docker-compose.yml`, although the code uses neither.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{"status":"ok","service":"memory"}` |
| POST | `/memory/session` | Append an entry | Body `MemoryWrite {agent_id: str, content: dict}`. The stored entry is `{**content, "ts": <unix float>}`. Returns `{"stored": true}`. |
| GET | `/memory/session/{agent_id}` | Read an agent's entries | A list of stored entries in insertion order. Returns `[]` for an unknown agent. |

There is no OpenAPI contract under `schemas/openapi/`.

## Configuration
No environment variables are read.

## Data & dependencies
- Storage is only the in-process dict `_SESSION_MEMORY: dict[str, list[dict]]`. It is lost on restart, not shared across replicas, and has no TTL or size limit.
- A `ts` key inside `content` is overwritten by the server timestamp.
- `schemas/sql/001_init.sql` defines a `memory_entries` table (with an `M1_SESSION`/`M2_EPISODIC`/`M3_SEMANTIC` layer check), but this service does not use it.
- It calls no services and uses no Kafka.
- Callers:
  - `platform/aepx-console` proxies POST and GET through `MEMORY_URL`.
  - `services/gateway` includes it in `/health`.
  - `services/workflow` reads `MEMORY_URL` but never calls it in its current code.

## Run & test
```bash
pip install -r services/memory/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/memory
cd services/memory && python -m pytest tests -v
```
Tests: health, then a write followed by a read that returns one entry.

Run it alone:
```bash
cd services/memory && uvicorn app.main:app --port 8004
curl -s -X POST http://localhost:8004/memory/session -H 'content-type: application/json' \
  -d '{"agent_id":"a1","content":{"turn":"hello"}}'
curl -s http://localhost:8004/memory/session/a1
```

## Changing it
- The request shape `{agent_id, content}` and the list response are used by `platform/aepx-console/app/main.py`. Grep with `grep -rn "MEMORY_URL\|/memory/session" services connector-bus sdk platform console`.
- To move to Postgres, use `memory_entries`. Its `agent_id` is a UUID `REFERENCES agents(id)`, so non-UUID agent ids such as `a1` (used in the tests) would fail. Plan a migration or fallback like the Registry/Trust degrade pattern.
- Tests share module state. Use distinct `agent_id`s, or the length assertions in `test_write_and_read_session` break.
- If the service gains real deps (Postgres/Redis), add them to `requirements.txt` and wire the env vars in `docker-compose.yml`. Today the compose `depends_on` is only ordering.

## Related skills
- aepx-svc-workflow (has `MEMORY_URL` configured)
- aepx-svc-cache (the sibling reuse layer)
- aepx-svc-gateway
- aepx-run-stack, aepx-test-component, aepx-ci-debug
