---
name: aepx-svc-gateway
description: AEP-X Gateway. It is the platform entrypoint on port 8000 that aggregates every service's /health and exposes /execute (registry lookup plus a cost-optimiser routing decision). Use when working on, debugging, calling or extending the gateway service, stack health aggregation or /execute routing in aepx-core.
---

# Gateway service (`services/gateway`)

## Role
Gateway is the single front door of the stack. `GET /health` fans out to every downstream service and reports each result, so it is the quickest whole-stack check. `POST /execute` looks up the agent in Registry, then asks Cost Optimiser which tier of the RFC-0008 reuse-before-computation hierarchy should serve the call (cache-first routing, Law 5). It returns that decision with the request. It does not yet *execute* the chosen tier.

## Where
- Code: `services/gateway/app/main.py`.
- Compose service: `gateway`. Host port `8000` maps to container port `8000`.
- `depends_on: [identity, trust, registry, memory, cache, discovery, workflow, safety, governance]`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Aggregate health | `{<service>: <that service's /health JSON>}` for each entry in `SERVICES`. A failure becomes `{status:"down", error:"..."}`. Each call has a 2s timeout and runs sequentially. |
| POST | `/execute` | Route a capability | Query `agent_id`, `capability`, optional `route` (one of `ROUTES`: cache, memory, knowledge, workflow, tool, small_model, medium_model, large_model, human; anything else returns 422). Body: a JSON object (`payload: dict`). Calls `GET {REGISTRY_URL}/agents/{agent_id}` (5s timeout), then `POST {COST_OPTIMISER_URL}/route/decide` once per candidate (2s each). Candidates are `DEFAULT_CANDIDATES` = cache, small_model, large_model, or just the pinned `route`. Returns `{agent, capability, payload, route}`, where `route` is `{status:"decided", selected, utility_score, explanation, scores:{tier: score}}`. A utility tie goes to the earlier (cheaper) tier. If Cost Optimiser is unreachable, `route` is `{status:"unavailable", error, candidates}` and the response is still HTTP 200. |

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
| `COST_OPTIMISER_URL` | `http://cost-optimiser:8000` (also used by `/execute` routing) |
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
The health tests expect every downstream to be unreachable and check that `registry`, `marketplace` and `billing` report `down`. They are slow-ish, because each service is tried in turn. The `/execute` tests monkeypatch `main.httpx.AsyncClient` with a fake client. They cover highest-utility selection, a tie going to the cheaper tier, a pinned route, an unknown route returning 422, and the Cost Optimiser-down degrade.

Run it alone or against the stack:
```bash
cd services/gateway && REGISTRY_URL=http://localhost:8003 TRUST_URL=http://localhost:8002 COST_OPTIMISER_URL=http://localhost:8012 uvicorn app.main:app --port 8000
curl -s http://localhost:8000/health
curl -s -X POST "http://localhost:8000/execute?agent_id=<id>&capability=generate" -H 'content-type: application/json' -d '{"prompt":"hi"}'
curl -s -X POST "http://localhost:8000/execute?agent_id=<id>&capability=generate&route=knowledge" -H 'content-type: application/json' -d '{}'   # pin one tier
```

## Changing it
- If you add a service to `/health`, add both the `SERVICES` entry and the env var in `docker-compose.yml` (and in `docker-compose.test.yml`, where it points at a stub target). The aggregate is keyed by the `SERVICES` name.
- If you change `/execute`, keep `agent_id`/`capability` as query params and keep the `agent`/`capability`/`payload` response keys, because the SDK depends on both. The next step is executing the selected tier, for example calling Cache on `cache`, or the `ml` connector via the bus on `*_model`. `ROUTES` must match `services/cost-optimiser`. Update `sdk/python/aepx/agent.py` if the shape changes. Grep with `grep -rn "gateway_url\|GATEWAY_URL\|/execute" sdk platform console`.
- The conformance check hits `/health`. Keep it returning 200 even when every downstream is down.
- The SDK default is `http://localhost:8000` (`sdk/python/aepx/client.py`). Keep the host port.

## Related skills
- aepx-svc-registry (`/execute` lookup)
- aepx-svc-identity, aepx-svc-trust, aepx-svc-memory, aepx-svc-cache, aepx-svc-discovery, aepx-svc-workflow, aepx-svc-safety (health targets)
- aepx-svc-cost-optimiser (`/execute` routing decision)
- aepx-svc-governance, aepx-svc-knowledge, aepx-svc-verification, aepx-svc-ml-integration (also health targets)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
