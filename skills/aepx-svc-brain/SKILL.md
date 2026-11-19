---
name: aepx-svc-brain
description: AEP-X Brain, the self-healing monitor that polls service health, re-warms Ollama and runs per-connector circuit breakers learned from Governance audit history. Use when working on, debugging, calling or extending the brain service in aepx-core, or when a connector is unexpectedly circuit-broken.
---

# Brain service (`services/brain`)

## Role
The Brain has two jobs, kept separate from Trust (which learns about agents):
- **Self-healing:** it polls the platform services' `/health`, re-warms a cold Ollama, and runs a circuit breaker for each connector.
- **Self-learning:** it derives each connector's reliability from Governance's real audit history, and persists circuit state so that learning survives a restart.

Every state transition is published to Kafka as a `brain.*` topic, so Governance audits it (Law 8). The Brain does not act silently. Compose deliberately gives it no `docker.sock`: it works over HTTP only.

## Where
- Code: `services/brain/app/main.py`.
- Compose service `brain`, host port **8014** -> container 8000, `depends_on: [postgres, governance, ollama]`.
- Environment in compose:
  - `DATABASE_URL`
  - `GOVERNANCE_URL=http://governance:8000`
  - `OLLAMA_URL=http://ollama:11434`
  - `OLLAMA_MODEL=llama3.2:1b`
  - `BRAIN_POLL_INTERVAL=20`

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"brain", persisted: bool, monitoring: <count of MONITORED_SERVICES>}` |
| GET | `/brain/status` | Per-service up/down view | `{services: {<name>: {up, consecutive_failures}}}` |
| GET | `/brain/circuit/{connector}` | Circuit state for one connector | `{connector, allowed: state != "open", state, consecutive_failures, reliability_score, opened_at}`. An unknown connector returns `closed` with `allowed: true` |
| GET | `/brain/reliability` | All connectors, least reliable first | `[{connector, reliability_score, state}]` |
| GET | `/brain/incidents?limit=100` | Incident log, newest first | `[{kind, target, detail, created_at}]` |

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://aepx:aepx_dev_only@postgres:5432/aepx` | Persists `brain.*` state |
| `GOVERNANCE_URL` | `http://governance:8000` | Source of the audit history (`GET /audit?limit=300`) |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama base URL |
| `OLLAMA_MODEL` | `llama3.2:1b` | Model used for the re-warm generate call |
| `BRAIN_POLL_INTERVAL` | `20` | Seconds between monitor cycles |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Broker for `brain.*` events (not set in compose) |

Constants in the code:
- `CIRCUIT_FAILURE_THRESHOLD=5`
- `CIRCUIT_COOLDOWN_SECONDS=60`
- `DOWN_THRESHOLD=3`: this many consecutive failed health checks marks a service down

`MONITORED_SERVICES` is a hard-coded map of names to `http://<name>:8000/health` URLs, not environment variables. It covers 16 services: identity, trust, registry, memory, cache, gateway, discovery, workflow, safety, governance, knowledge, verification, cost-optimiser, ml-integration, connector-bus and console. It does **not** include marketplace, billing, oracle-bridge or brain itself.

## Data & dependencies
- **Postgres** (`schemas/sql/006_brain.sql`):
  - `brain.incidents`, with `kind CHECK IN (service_down, service_recovered, ollama_rewarmed, circuit_opened, circuit_closed, circuit_half_open)`
  - `brain.circuit_state`, with `connector PK`, `state CHECK IN (closed, open, half_open)`, `consecutive_failures`, `reliability_score`, `opened_at` and `updated_at`
- **In-memory fallback:** `_circuit_fallback` and `_incidents_fallback` are used when Postgres is unreachable. `_service_state` is always in memory.
- **Kafka (publishes):** `brain.<kind>` for every incident, with payload `{target, detail, ts}`.
- **Monitor loop:** a daemon thread started at import. Each cycle runs `_check_services`, then `_check_ollama`, then `_recompute_reliability_and_circuits`, and swallows all exceptions.
- **Ollama re-warm:** if `GET {OLLAMA_URL}/api/tags` fails, the Brain POSTs `/api/generate` with a 45 s timeout. On success it records `ollama_rewarmed`.
- **Learning:**
  - It reads Governance `/audit`, which returns newest first.
  - It keeps only `connector.*` topics and reads `event.connector` and `event.outcome`. Success means `outcome == "invoked"`. These events are emitted by `connector-bus` `_audit()`.
  - `reliability` is the success ratio.
  - `consecutive_failures` counts failures from the newest event backwards.
  - Transitions: closed goes to open when failures reach the threshold. open goes to half_open after the cooldown. half_open goes to closed or open depending on the newest outcome.
- **Governance down:** the recompute step returns early and circuits keep their last state.
- **Caller:** `connector-bus` calls `GET /brain/circuit/{name}` before forwarding each call. It is **fail-open**: if the Brain is unreachable, the call proceeds. A 503 is returned only when `allowed` is false. `platform/aepx-console` proxies `/brain/status` and `/brain/reliability`.

## Run & test
```bash
pip install -r services/brain/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/brain
cd services/brain && python -m pytest tests -v
```
The tests use the in-memory fallbacks and monkeypatch `main.httpx.get` to feed fake audit history into `_recompute_reliability_and_circuits()`.

Run on its own. Outside compose, the hard-coded service hostnames will not resolve, so every service shows down after 3 polls:
```bash
cd services/brain && GOVERNANCE_URL=http://localhost:8009 OLLAMA_URL=http://localhost:11434 \
  uvicorn app.main:app --port 8014
curl -s localhost:8014/health
curl -s localhost:8014/brain/status
curl -s localhost:8014/brain/circuit/ml
curl -s localhost:8014/brain/reliability
curl -s "localhost:8014/brain/incidents?limit=20"
```

## Changing it
- **A new incident kind needs changes in three places**, or its events are silently lost from the audit trail. A shipped bug came from exactly this.
  1. The `CHECK` in `schemas/sql/006_brain.sql`, through a new migration.
  2. Governance `_CONSUMED_TOPICS`.
  3. The `brain_kinds` list in `services/governance/tests/test_health.py::test_consumes_every_brain_topic`.
- The `/brain/circuit/{connector}` shape (`allowed`, `reliability_score`) is read by `connector-bus/app/main.py`. Keep it additive only.
- If you change the audit event fields that connector-bus emits (`connector`, `outcome`), update the learning logic here too.
- To monitor a new service, add it to `MONITORED_SERVICES`. `test_brain_status_shape` compares against that dict.
- Don't give the Brain Docker or host control. Its actions must stay auditable HTTP calls and Kafka events.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "BRAIN_URL\|/brain/" services connector-bus sdk platform console`.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-governance: audit source, and consumes `brain.*`
- aepx-connector-adapter: the connectors the circuits protect
- aepx-governance-policy
