---
name: aepx-svc-gateway
description: AEP-X Gateway. It is the platform entrypoint on port 8000 that aggregates every service's /health and exposes /execute (currently a registry-lookup passthrough). Use when working on, debugging, calling or extending the gateway service, stack health aggregation or /execute routing in aepx-core.
---

# Gateway service (`services/gateway`)

## Role
Gateway is the single front door of the stack. `GET /health` fans out to every downstream service and reports each result, so it is the quickest whole-stack check. `POST /execute` is a v0.0.1 passthrough: it looks up the agent in Registry and echoes the request back. The code comment says cache-first routing (the RFC-0008 hierarchy, now implemented by `services/cost-optimiser`) will land here once it is wired.

## Where
- Code: `services/gateway/app/main.py`.
- Compose service: `gateway`. Host port `8000` maps to container port `8000`.
- `depends_on: [identity, trust, registry, memory, cache, discovery, workflow, safety, governance]`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Aggregate health | `{<service>: <that service's /health JSON>}` for each entry in `SERVICES`. A failure becomes `{status:"down", error:"..."}`. Each call has a 2s timeout and runs sequentially. |
| POST | `/execute` | Execute a capability (stub) | Query `agent_id`, `capability`. Body: a JSON object (`payload: dict`). Calls `GET {REGISTRY_URL}/agents/{agent_id}` (5s timeout). Returns `{agent: <registry JSON>, capability, payload}`. |

There is no OpenAPI contract under `schemas/openapi/`.

## Configuration
Each variable is the base URL of a service in `SERVICES`, polled by `/health`.

| Name | Default (from code) |
|---|---|
| `IDENTITY_URL` | `http://identity:8000` |
| `TRUST_URL` | `http://trust:8000` |
| `REGISTRY_URL` | `http://registry:8000` (also used by `/execute`) |
| `MEMORY_URL` | `http://memory:8000` |
| `CACHE_URL` | `http://cache:8000` |
| `DISCOVERY_URL` | `http://discovery:8000` |
| `WORKFLOW_URL` | `http://workflow:8000` |
| `SAFETY_URL` | `http://safety:8000` |
| `GOVERNANCE_URL` | `http://governance:8000` |
| `KNOWLEDGE_URL` | `http://knowledge:8000` |
| `VERIFICATION_URL` | `http://verification:8000` |
| `COST_OPTIMISER_URL` | `http://cost-optimiser:8000` |
| `ML_INTEGRATION_URL` | `http://ml-integration:8000` |
| `ORACLE_BRIDGE_URL` | `http://oracle-bridge:8000` |
| `MARKETPLACE_URL` | `http://marketplace:8000` |
| `BILLING_URL` | `http://billing:8000` |
| `CONNECTOR_BUS_URL` | `http://connector-bus:8000` |

Brain (:8014) is the one service not in `SERVICES`; check it directly.

## Data & dependencies
- It is stateless and uses no storage or Kafka.
- `/health` never raises for a down dependency, because each service is caught individually. Total latency grows with the number of unreachable services (up to about 2s each).
- `/execute` does not check the Registry status code. A 404 agent comes back as `agent: {"detail":"agent not found"}` with HTTP 200. If Registry is unreachable, the handler raises (500).
- Callers:
  - `sdk/python/aepx/agent.py` `Agent.execute()` (POST `/execute`, `params={agent_id, capability}`, `json={"prompt": ...}`)
  - `sdk/python/aepx/conformance/checks.py` (`GET /health`)
  - `platform/workbench`, `platform/conformance`, `platform/aepx-console` (`GATEWAY_URL`)
- `docker-compose.test.yml` points unused service URLs at `identity-test` as stub targets.

## Run & test
```bash
pip install -r services/gateway/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/gateway
cd services/gateway && python -m pytest tests -v
```
The test expects every downstream to be unreachable and checks that `body["registry"]["status"] == "down"`. It is slow-ish, because each service is tried in turn.

Run it alone or against the stack:
```bash
cd services/gateway && REGISTRY_URL=http://localhost:8003 TRUST_URL=http://localhost:8002 uvicorn app.main:app --port 8000
curl -s http://localhost:8000/health
curl -s -X POST "http://localhost:8000/execute?agent_id=<id>&capability=generate" -H 'content-type: application/json' -d '{"prompt":"hi"}'
```

## Changing it
- If you add a service to `/health`, add both the `SERVICES` entry and the env var in `docker-compose.yml` (and in `docker-compose.test.yml`, where it points at a stub target). The aggregate is keyed by the `SERVICES` name.
- If you change `/execute` (for example, wiring in Cost Optimiser `/route/decide`), keep `agent_id`/`capability` as query params, because the SDK sends them that way. Update `sdk/python/aepx/agent.py` if the shape changes. Grep with `grep -rn "gateway_url\|GATEWAY_URL\|/execute" sdk platform console`.
- The conformance check hits `/health`. Keep it returning 200 even when every downstream is down.
- The SDK default is `http://localhost:8000` (`sdk/python/aepx/client.py`). Keep the host port.

## Related skills
- aepx-svc-registry (`/execute` lookup)
- aepx-svc-identity, aepx-svc-trust, aepx-svc-memory, aepx-svc-cache, aepx-svc-discovery, aepx-svc-workflow, aepx-svc-safety (health targets)
- aepx-svc-governance, aepx-svc-knowledge, aepx-svc-verification, aepx-svc-cost-optimiser, aepx-svc-ml-integration (also health targets)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
