---
name: aepx-run-stack
description: Bring up, health-check, and tear down the AEP-X stack (aepx-core) locally with Docker Compose, or a subset of it. Use when asked to run, start, deploy locally, or smoke-test AEP-X services, connectors, or the consoles.
---

# Run the AEP-X stack

Work from the aepx-core repo root.

## Full stack

```bash
cp -n .env.example .env        # first run only
docker compose up --build -d
curl -s http://localhost:8000/health   # Gateway aggregates every service's health
```

Then open the AEP-X Console at http://localhost:8083.

## Subset (SOA layer on a healthy core)

Dependency order matters (SOA-Architecture.md §5): trust and governance first, then the bus and category services.

```bash
docker compose up -d postgres redis trust governance
docker compose up --build -d connector-bus connector-enterprise connector-aiplatform connector-devtools connector-productivity
```

## Port map (host → container 8000)

| Port | Service | Port | Service |
|---|---|---|---|
| 8000 | gateway | 8010 | knowledge |
| 8001 | identity | 8011 | verification |
| 8002 | trust | 8012 | cost-optimiser |
| 8003 | registry | 8013 | ml-integration |
| 8004 | memory | 8014 | brain |
| 8005 | cache | 8015 | oracle-bridge |
| 8006 | discovery | 8016 | marketplace |
| 8007 | workflow | 8017 | billing |
| 8008 | safety | 8020 | connector-bus |
| 8009 | governance | 8021–8031 | connector-{enterprise, aiplatform, devtools, productivity, data, messaging, industrial, cloud, government, education, blockchain} |

GUIs: 8080 LLM console, 8081 Workbench, 8082 Conformance, 8083 AEP-X Console.
Infra: 5432 Postgres (pgvector), 6379 Redis, 7474/7687 Neo4j, 9092 Kafka, 11434 Ollama.

## Health sweep

```bash
for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012 8013 8014 8015 8016 8017 8020; do
  printf "%s " $p; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:$p/health
done
```

A non-200 → `docker compose logs --tail 80 <service>`.

## Without Docker

Each service is a FastAPI app. From `services/<name>/`: `pip install -r requirements.txt` then `uvicorn app.main:app --port <port>`. Point it at real Postgres+pgvector and Redis via the env vars in `.env.example`.

## Tear down

`docker compose down` (add `-v` only if the user wants volumes wiped — it deletes Postgres data and uploads).
