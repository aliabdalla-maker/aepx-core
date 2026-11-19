---
name: aepx-database
description: AEP-X data stores — schemas/sql/*.sql (tables per file, pgvector), how Postgres applies them via docker-entrypoint-initdb.d, adding a migration safely, and connecting to local Postgres/Redis/Neo4j/Kafka from docker-compose. Use when changing schema, writing SQL, or inspecting local data.
---

# AEP-X databases and migrations

## Schema files (`schemas/sql/`)

| File | Creates / changes |
|---|---|
| `001_init.sql` | `pgcrypto` extension; tables `agents`, `capabilities`, `agent_capabilities`, `trust_scores`, `memory_entries` (public schema) |
| `002_v2_additions.sql` | `vector` extension; schemas and tables `knowledge.entries` (`embedding VECTOR(1536)`), `verification.results` (band CHECK: GREEN/AMBER/RED/GREY), `ml.models`; per-service roles are only **commented out** |
| `003_connectors.sql` | `connectors.registry` and `connectors.audit_log`, with catalogue rows INSERTed. Its header says it is **generated from `connectors/catalogue.json`, regenerate rather than hand-edit**. It **DROPs** both tables before recreating them. No generator script exists in the repo. |
| `004_governance_audit.sql` | `governance.audit_log` (BIGSERIAL `id`, `topic`, `event JSONB`, `recorded_at`), plus an index on `recorded_at DESC` |
| `005_trust_entity_id_text.sql` | `ALTER TABLE trust_scores ALTER COLUMN entity_id TYPE TEXT` (wire IDs like `aepx://agent/console` are not UUIDs) |
| `006_brain.sql` | `brain.incidents` (with a `kind` CHECK list), `brain.circuit_state` |
| `007_blockchain.sql` | Widens the `connectors.registry` category CHECK to include `blockchain` (finds the old constraint name dynamically); INSERTs the 7 blockchain connectors; creates `governance.ledger_anchors`; `ALTER TABLE agents ADD COLUMN IF NOT EXISTS did TEXT UNIQUE` |

**pgvector.** 002 needs the `vector` extension, so compose uses `pgvector/pgvector:pg16` rather than stock postgres. With stock postgres the init fails with `extension "vector" is not available` (Operational Manual §6). The only vector column is `knowledge.entries.embedding`. The Knowledge service is still a substring-match scaffold that does not query it yet.

**Who actually connects**, via `DATABASE_URL`, default `postgresql://aepx:aepx_dev_only@postgres:5432/aepx`: `trust`, `registry`, `governance` and `brain`. Each one falls back to in-memory state if Postgres cannot be reached. Memory and Knowledge currently keep in-process dicts.

## How migrations are applied

`docker-compose.yml` mounts `./schemas/sql:/docker-entrypoint-initdb.d`. `docker-compose.test.yml`'s `postgres-test` (host port 5532) does the same. The Postgres image runs those files **in filename order, only when the data directory is empty**, which is why files carry a numeric prefix. There is no migration tool or version table. Per Operational Manual §4.1 and §7:

```bash
docker compose down -v        # full reset incl. data volumes — Postgres re-runs schemas/sql/*.sql on next start
docker compose up -d postgres
```

Against an **existing** database, a new file is not applied automatically. Run it by hand:

```bash
docker compose exec -T postgres psql -U aepx -d aepx < schemas/sql/008_<name>.sql
```

## Adding a migration safely

1. Create the next number, `schemas/sql/008_<short_name>.sql`. Never edit an already-shipped file to change behaviour, because existing databases never re-run it.
2. Make it **additive and idempotent**, because it may run both on fresh init and by hand:
   - `CREATE SCHEMA IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`
   - `ADD COLUMN IF NOT EXISTS`, with new columns nullable
   - for constraint changes, the dynamic `DO $$ ... $$` lookup from 007
3. Start the file with a comment explaining why it exists, as every existing file does.
4. Put a service's tables in **that service's own schema** (database-per-service, Law 10). Do not add cross-schema foreign keys.
5. Watch the CHECK constraints that encode enumerations:
   - A new connector category needs the category CHECK widened (as in 007).
   - A new Brain incident kind needs `brain.incidents.kind` widened. Also add the matching Kafka topic to Governance's `_CONSUMED_TOPICS`.
6. Do **not** re-run 001 (plain `CREATE TABLE` fails on re-run) or 003 (it drops `connectors.registry` and `connectors.audit_log`, and would also drop 007's blockchain rows) against a live database.
7. Test it from scratch with `docker compose down -v && docker compose up -d postgres`, then `docker compose logs postgres` to confirm every file ran. Then run the owning service's tests. Unit tests do not use Postgres, so this manual check is the only real verification.
8. Update the RFC §5 "Data Model / Schema" section that the change belongs to.

`down -v` wipes **all** volumes, including `ollama-models` and `console-uploads`. Ask the user before running it on a stack with data they care about.

## Connecting locally (from `docker-compose.yml`)

| Store | Host access | Credentials / notes |
|---|---|---|
| Postgres | `localhost:5432`, db `aepx` | user `aepx`, password `aepx_dev_only`; `docker compose exec postgres psql -U aepx -d aepx` |
| Redis | `localhost:6379` | no auth; `docker compose exec redis redis-cli`. Used by cache and discovery (`REDIS_HOST`, default `redis`) |
| Neo4j | browser `http://localhost:7474`, Bolt `localhost:7687` | `NEO4J_AUTH=neo4j/aepx_dev_only`. `workflow` `depends_on` it, but no service code references Neo4j yet |
| Kafka (KRaft) | `9092` published | advertised listener is `PLAINTEXT://kafka:9092`, so clients should run inside the compose network, e.g. `docker compose exec kafka kafka-topics --bootstrap-server kafka:9092 --list`. Services use `KAFKA_BOOTSTRAP` (default `kafka:9092`) |

These credentials are dev-only (`aepx_dev_only`). Do not reuse them outside local development.

Useful queries:

```sql
SELECT id, topic, recorded_at FROM governance.audit_log ORDER BY recorded_at DESC LIMIT 20;
SELECT seq_no, entry_count, backend, tx_ref FROM governance.ledger_anchors ORDER BY seq_no DESC;
SELECT entity_id, behaviour_score FROM trust_scores LIMIT 20;
```

## Related skills

- `aepx-new-service` — schema for a new service
- `aepx-run-stack` — starting and resetting the stack
- `aepx-blockchain` — `ledger_anchors` and `agents.did`
- `aepx-governance-policy` — the audit trail semantics
- `aepx-connector-adapter` — catalogue changes behind `connectors.registry`
- `aepx-svc-trust`, `aepx-svc-registry`, `aepx-svc-governance` — the DB-backed services
