---
name: aepx-svc-knowledge
description: Knowledge Service for AEP-X, which stores validated facts and source documents and offers a simple search (currently an in-memory scaffold). Use when working on, debugging, calling or extending the knowledge service in aepx-core, or when moving it onto Postgres/pgvector.
---

# Knowledge Service (`services/knowledge`)

## Role
This service owns the platform's validated facts, source documents and knowledge embeddings (docs/Microservices-Architecture-v2.md §3). That doc describes it as distinct from the Memory Service. Its intended callers are Workflow Engine and Verification Engine, which call it synchronously (§4.2). In its current form it is a **scaffold**:
- entries are held in a process-local dict
- search is a naive substring match, which the code flags to be swapped for pgvector cosine similarity "before the Alpha Gate"

## Where
- Code: `services/knowledge/app/main.py`. `app/models.py` is a placeholder reserved for future SQLAlchemy models.
- Compose service `knowledge`, host port **8010** -> container 8000, `depends_on: [postgres]`. The current code does not connect to Postgres.
- No environment block in docker-compose.yml.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"knowledge"}` |
| POST | `/knowledge` | Create an entry | JSON `KnowledgeIn`: `{title, content, source, confidence=0.8}`. Returns `Knowledge`: the same fields plus `id` (uuid4 str), `trust_score=50`, `created_at` (epoch float) |
| GET | `/knowledge/{knowledge_id}` | Fetch one entry | Returns `Knowledge`, or 404 `"not found"` |
| POST | `/knowledge/search` | Search entries | **Query params** `query` (required) and `limit=5`. Case-insensitive substring match on `content` only (not `title`). Returns `{query, results:[Knowledge]}` |

## Configuration
The code reads no environment variables.

## Data & dependencies
- **Storage:** the in-memory `_KNOWLEDGE: dict[str, Knowledge]`. Everything is lost on restart, and nothing is shared between replicas.
- **Planned schema (not yet used by the code):** `knowledge.entries` in `schemas/sql/002_v2_additions.sql`, with columns `id UUID, title, content, source, confidence NUMERIC DEFAULT 0.8, embedding VECTOR(1536), created_at`. This is why compose uses the `pgvector/pgvector:pg16` image. The table has no `trust_score` column, although the API model has one.
- **Other services:** it calls none. `httpx` is in requirements.txt but is not imported.
- **Kafka:** it publishes and consumes nothing.
- **Monitoring:** the Gateway `/health` aggregate (`KNOWLEDGE_URL`) and the Brain monitor both poll its `/health`. `platform/aepx-console` also lists it.

## Run & test
```bash
pip install -r services/knowledge/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/knowledge
cd services/knowledge && python -m pytest tests -v
```

Run on its own:
```bash
cd services/knowledge && uvicorn app.main:app --port 8010
curl -s localhost:8010/health
curl -s -X POST localhost:8010/knowledge -H 'Content-Type: application/json' \
  -d '{"title":"Newton","content":"F = ma","source":"physics-101"}'
curl -s -X POST "localhost:8010/knowledge/search?query=ma&limit=5"
curl -s localhost:8010/knowledge/<id>
```

## Changing it
- `/knowledge/search` takes `query` and `limit` as **query parameters**, not a JSON body. Keep that, or update the test and any caller together.
- Moving to Postgres:
  - Use the `knowledge` schema only. Database-per-service applies (schemas/sql/002 comments; Microservices guide §4.3).
  - Decide what happens to `trust_score`, which is not in `knowledge.entries`.
  - Put the models in `app/models.py`.
  - Add `psycopg` to requirements.txt.
  - Keep a fallback so `/health` and the tests still pass without Postgres. Other services, such as governance and brain, report `persisted` for this.
- An embedding change must match `VECTOR(1536)`, or it needs a new migration file in `schemas/sql/`. Never edit an already-applied migration.
- Verification is documented as the reader of Knowledge, but `services/verification` does not call it yet. Its `truth_score` is a placeholder. Wiring the two together changes Verification's scores.
- No code in services/, connector-bus/, sdk/, platform/ or console/ calls `/knowledge` endpoints today. Recheck with `grep -rn "/knowledge" services connector-bus sdk platform console`.
- There is no OpenAPI contract in `schemas/openapi/` for this service.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-verification: the documented consumer of knowledge evidence
- aepx-svc-brain: monitors its health
