---
name: aepx-svc-cost-optimiser
description: Cost Optimiser for AEP-X. It computes a Utility Score for a candidate route (cache, memory, a model tier or a human) using the caller's Trust score, under Law 5 (Reuse Before Computation). Use when working on, debugging, calling or extending the cost-optimiser service in aepx-core.
---

# Cost Optimiser service (`services/cost-optimiser`)

## Role
This service owns Utility Score computations and routing decisions (docs/Microservices-Architecture-v2.md §3). The score is:

Accuracy + Trust + Compliance + Performance − Cost − Latency − Energy − Risk.

Its explanation text cites Law 5 (Reuse Before Computation): "Routing chooses highest utility, not highest intelligence".

The docs make it the one deliberate synchronous Tier 2 service. The Gateway is meant to call `POST /route/decide` before an LLM call, with a budget under 20 ms (§4.1). The Gateway now does this: `/execute` posts one `/route/decide` per candidate tier (default `cache`, `small_model`, `large_model`, or the single `route` the caller pins) and returns the highest-utility tier. Each call has a 2s timeout, and there is no 20 ms budget enforcement yet.

## Where
- Code: `services/cost-optimiser/app/main.py`.
- Compose service `cost-optimiser`, host port **8012** -> container 8000.
- Environment `TRUST_URL=http://trust:8000`.
- `depends_on: [trust, redis]`. The code does not use Redis.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"cost-optimiser"}` |
| POST | `/route/decide` | Score one candidate route | Request is `RouteRequest`: `{agent_id, capability, candidate_route, estimated_cost=0.0, estimated_latency_ms=0.0, estimated_energy=0.0}`. Response is `{agent_id, candidate_route, utility_score, breakdown (the WEIGHTS dict), explanation}` |

- **Routes:** `ROUTES = [cache, memory, knowledge, workflow, tool, small_model, medium_model, large_model, human]`. `candidate_route` is **not** validated against this list.
- **Weights:** `WEIGHTS = {accuracy 0.25, trust 0.20, compliance 0.15, performance 0.10, cost -0.15, latency -0.05, energy -0.05, risk -0.05}`. The code says to tune these with pilot data and not treat them as a guarantee.
- **Terms in `utility_score()`:**
  - `accuracy` is a placeholder fixed at 0.9.
  - `compliance` is 0.9 for `large_model` and 1.0 otherwise.
  - `performance` is `1 - min(latency_ms/1000, 1)`.
  - `risk` is 0.1 for `human` and 0 otherwise.
  - `trust` is `trust_score/100`.
  - `cost` and `energy` are used as given.
  - `latency` is `latency_ms/1000`.

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `TRUST_URL` | `http://trust:8000` | Trust Authority base URL. The service calls `GET {TRUST_URL}/trust/{agent_id}` |

## Data & dependencies
- **Storage:** none. Each decision is a pure function of the request and the Trust response. The docs plan a Redis cache for routing decisions, but it is not implemented.
- **Trust:** the service calls Trust on every request with a 2 s timeout. If the Trust JSON has no `trust_score` key, it uses 50.
- **Failure behaviour:** the Trust call is **not** wrapped in try/except. If Trust is unreachable or returns non-JSON, the exception propagates and the request fails with a 5xx. It does not degrade gracefully.
- **Kafka:** none. `ml.prediction.made` is documented as an optional input, but the service does not consume it.
- **Callers:** `services/gateway` `/execute` (`_decide_route`) calls `/route/decide`. Brain and the aepx-console poll `/health` only.
- Gateway keeps its own copy of `ROUTES` so it can reject an unknown `route` with a 422. If you change `ROUTES` here, change it in `services/gateway/app/main.py` too.

## Run & test
```bash
pip install -r services/cost-optimiser/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/cost-optimiser
cd services/cost-optimiser && python -m pytest tests -v
```
The test patches `httpx.AsyncClient.get`, so Trust does not need to be running.

Run on its own. Trust must be reachable at `TRUST_URL`, or `/route/decide` errors:
```bash
cd services/cost-optimiser && TRUST_URL=http://localhost:8002 uvicorn app.main:app --port 8012
curl -s localhost:8012/health
curl -s -X POST localhost:8012/route/decide -H 'Content-Type: application/json' \
  -d '{"agent_id":"agent-1","capability":"lesson_generation","candidate_route":"cache","estimated_latency_ms":5}'
```

## Changing it
- Read Trust **through its API**, never from the `trust_scores` table directly. The docs call this out explicitly. The latency budget is meant to be met by caching the Trust *response*.
- If you add error handling around the Trust call, decide whether to fail open (default score) or fail closed. Then add a test for it, because none exists today.
- `breakdown` returns the raw `WEIGHTS`, not the per-term contributions. Changing that changes the response shape.
- If you wire it into the Gateway, justify the synchronous Tier 2 exception in the PR, per docs/Microservices-Architecture-v2.md §4.1.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "route/decide\|COST_OPTIMISER_URL" services connector-bus sdk platform console`.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-ml-integration: `/recommend` defaults to the cheapest route and is the intended source of learned routing
- aepx-svc-verification: the intended source for the `accuracy` term
