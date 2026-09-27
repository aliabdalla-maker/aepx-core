---
name: aepx-svc-discovery
description: AEP-X Discovery service. It ranks registered agents by a weighted score using live Trust scores, and caches results in Redis for 30s. Use when working on, debugging, calling or extending the discovery service, agent ranking or /discover in aepx-core.
---

# Discovery service (`services/discovery`)

## Role
Discovery answers "which agent should handle this?". It fetches every agent from Registry, looks up each one's trust score in Trust, computes a weighted score and returns the list sorted best-first. Results are cached per capability in Redis. It is a Tier 1 (synchronous) service in `docs/Microservices-Architecture-v2.md`.

## Where
- Code: `services/discovery/app/main.py`.
- Compose service: `discovery`. Host port `8006` maps to container port `8000`.
- `depends_on: [registry, trust, redis]`. Compose sets no env vars, so the code defaults apply.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{"status":"ok","service":"discovery"}` (no dependency checks) |
| GET | `/discover` | Ranked agents | Query `capability` (required). Returns `{results: [<registry Agent fields> + score: float], cache_hit: bool}` sorted by `score` desc. |

Score (`score(agent, trust)`):
```
0.40*confidence + 0.25*(trust_score/100) + 0.15*availability - 0.10*(latency_ms/1000) - 0.10*cost
```
- The defaults are `confidence=0.8`, `trust_score=50`, `latency_ms=50` and `cost=0.0`.
- `availability` is a hard-coded `1.0` placeholder "until health-aggregation feeds this".
- Registry's `Agent` model has no `confidence`, `latency_ms` or `cost` fields, so in practice only the trust term varies.

There is no OpenAPI contract under `schemas/openapi/`.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `REDIS_HOST` | `redis` | Redis host (default port) |
| `REGISTRY_URL` | `http://registry:8000` | Source of `GET /agents` |
| `TRUST_URL` | `http://trust:8000` | `GET /trust/{agent_id}` per agent |

## Data & dependencies
- Redis key `discover:{capability}` holds the JSON ranked list, with `ex=30` seconds. A hit returns `cache_hit: true` without calling Registry or Trust.
- `capability` is used **only** as the cache key. Agents are not filtered by capability.
- It makes one Trust call per agent, sequentially, with a 3s client timeout. Latency scales with the agent count.
- There is no degrade path. If Registry, Trust or Redis is down, `/discover` raises a 500. (Trust itself fails open to defaults, so Trust rarely errors.)
- There is no Kafka.
- Callers: `platform/aepx-console` (`/api/discover` passes `capability` through) and `services/gateway` (`/health`).

## Run & test
```bash
pip install -r services/discovery/requirements.txt pytest httpx2 ruff==0.16.0
pip install fakeredis==2.37.0
ruff check services/discovery
cd services/discovery && python -m pytest tests -v
```
The tests replace `main.r` with `fakeredis.FakeRedis(decode_responses=True)`. They check health and that `score()` prefers higher trust. There is no HTTP-level `/discover` test.

Run it alone (needs Registry and Trust reachable):
```bash
docker compose up -d redis registry trust
cd services/discovery && REDIS_HOST=localhost REGISTRY_URL=http://localhost:8003 TRUST_URL=http://localhost:8002 \
  uvicorn app.main:app --port 8006
curl -s "http://localhost:8006/discover?capability=tutoring"
```

## Changing it
- If you change weights or terms in `score()`, keep `test_score_prefers_higher_trust` valid. The docs describe the routing utility weights separately (Cost Optimiser), so do not conflate the two.
- Results spread the whole Registry agent dict, so Registry `Agent` field changes flow straight into this response.
- The cache means ranking changes (new agents, trust adjustments) show up only after up to 30s.
- If you add capability filtering, you also need capability data on agents. Registry does not store it today, and `capabilities` in `001_init.sql` is not read by Registry.
- Keep Redis access through the module-level `r` so the fakeredis patch in tests keeps working.

## Related skills
- aepx-svc-registry, aepx-svc-trust (the upstreams it calls)
- aepx-svc-cache (the same Redis/fakeredis testing pattern)
- aepx-svc-gateway
- aepx-run-stack, aepx-test-component, aepx-ci-debug
