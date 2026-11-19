---
name: aepx-run-stack
description: Bring up, health-check, smoke-test and tear down the AEP-X stack (aepx-core) locally with Docker Compose — full stack, a subset, or the opt-in live-chain mode. Use when asked to run, start, deploy locally, or smoke-test AEP-X services, connectors, or the consoles.
---

# Run the AEP-X stack

Work from the aepx-core repo root. Start with `aepx-architecture` if you need the big picture.

## Full stack

```bash
cp -n .env.example .env        # first run only — compose reads .env for ${...} substitution
docker compose up --build -d
curl -s http://localhost:8000/health   # Gateway aggregates the core services' health
```

Then open the AEP-X Console at http://localhost:8083.

The Gateway's aggregated `/health` covers every core service, marketplace, billing and the bus, but **not** brain. Check brain (:8014) directly — see the sweep below.

## Subset (SOA layer on a healthy core)

Dependency order matters (SOA-Architecture.md §5): trust and governance first, then the bus and category services.

```bash
docker compose up -d postgres redis kafka trust governance
docker compose up --build -d connector-bus connector-enterprise connector-aiplatform connector-devtools connector-productivity
```

The bus publishes audit events to Kafka but does not `depends_on` it; if Kafka is down, audit events are silently dropped. Bring Kafka up whenever you need the audit trail.

## Live-chain mode (RFC-0006 / RFC-0008, opt-in)

The default stack runs with no chain; on-chain paths degrade cleanly. To run them for real:

```bash
docker compose -f docker-compose.yml -f docker-compose.chain.yml up -d anvil
python scripts/deploy_contracts.py --rpc http://localhost:8545     # writes .env.chain
docker compose --env-file .env.chain -f docker-compose.yml -f docker-compose.chain.yml up --build
```

Details and caveats: `aepx-blockchain`.

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

GUIs: 8080 LLM console, 8081 Workbench, 8082 Conformance, 8083 AEP-X Console (`aepx-consoles`).
Infra: 5432 Postgres (pgvector), 6379 Redis, 7474/7687 Neo4j, 9092 Kafka, 11434 Ollama. Chain overlay: 8545 anvil.

## Health sweep

```bash
for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012 8013 8014 8015 8016 8017 8020 8021 8022 8023 8024 8025 8026 8027 8028 8029 8030 8031; do
  printf "%s " $p; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:$p/health
done
```

A non-200 → `docker compose logs --tail 80 <service>`. Per-service behaviour and degrade rules are in each `aepx-svc-<name>` skill.

## Smoke test

- Protocol conformance against the live stack: `aepx test` (see `aepx-cli`) or the Conformance UI on :8082.
- A governed connector call: `aepx invoke salesforce --payload '{"op":"lookup_contact"}'`. New senders start at trust 50, so connectors needing 60/70 return 403 until trust rises — that's expected, not a failure.

## Without Docker

Each service is a FastAPI app. From `services/<name>/`: `pip install -r requirements.txt` then `uvicorn app.main:app --port <port>`. Most services fall back to in-memory state without Postgres/Redis; the env var names and defaults are in each `aepx-svc-<name>` skill and `.env.example`.

## Tear down

`docker compose down` (add `-v` only if the user wants volumes wiped — it deletes the downloaded Ollama models and console uploads; Postgres has no named volume, so its data is lost on any `down` anyway; ask first).

## Related skills

- aepx-architecture, aepx-consoles, aepx-blockchain, aepx-cli
- aepx-test-component, aepx-ci-debug
- aepx-svc-gateway, aepx-connector-bus, aepx-database
