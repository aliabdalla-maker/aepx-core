---
name: aepx-svc-cache
description: AEP-X Cache service. It is a Redis-backed key-value cache with the canonical RFC-0005 layers L0-L4 (fixed TTLs) and a policy-gated L5 federation layer, plus a legacy /cache/{key} L1 alias. Use when working on, debugging, calling or extending the cache service or cache layers in aepx-core.
---

# Cache service (`services/cache`)

## Role
Cache is a deliberately simple per-layer key-value store in Redis. It implements the canonical L0-L5 cache layers from RFC-0005 and ADLC Plan §15.3, as documented in `docs/Microservices-Architecture-v2.md` §4.3. It supports Law 5, Reuse Before Computation (cache comes first in that ordering). The Cost Optimiser, not this service, decides which layer to check.

## Where
- Code: `services/cache/app/main.py` (version `0.2.0`).
- Compose service: `cache`. Host port `8005` maps to container port `8000`.
- `depends_on: [redis]`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness and Redis check | `{status:"ok", service:"cache", redis: <ping bool>, layers:["L0".."L4","L5"]}` |
| GET | `/cache/{layer}/{key}` | Read | Returns `{layer, key, value: <json or null>, hit: bool}`. Returns 400 on an unknown layer. |
| POST | `/cache/{layer}/{key}` | Write | Body: a JSON object (`value: dict`). Query `l5_policy_allowed` (bool, default false). Returns `{stored:true, layer, ttl}`. L5 without the flag returns **403** `L5_policy_denied: ...`. An unknown layer returns 400. |
| GET | `/cache/{key}` | Legacy read | The same as `GET /cache/L1/{key}` |
| POST | `/cache/{key}` | Legacy write | Body is a dict. Query `ttl` (default 3600). Writes `L1:{key}` and returns `{stored:true, ttl}`. |

Layer TTLs (`CACHE_LAYERS`):

| Layer | Scope | TTL |
|---|---|---|
| L0 | Prompt | 300 |
| L1 | Session | 3600 |
| L2 | Agent | 86400 |
| L3 | Workflow | 604800 |
| L4 | Organisation | 2592000 |
| L5 | Federation | None (stored with no expiry) |

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `REDIS_HOST` | `redis` | Redis host. The port is hard-coded to `6379`, with `decode_responses=True`. |

## Data & dependencies
- Redis keys are `"{layer}:{key}"` (for example `L1:foo`), with JSON-encoded values.
- It calls no services and uses no Kafka.
- L5 enforcement is caller-attested. The service trusts the `l5_policy_allowed` query flag and does not call Governance itself.
- There is no degrade path. The Redis client is created at import, and any Redis outage surfaces as a 500 on every route, including `/health` (`r.ping()` raises).
- Callers: `services/gateway` (`/health`) and `platform/aepx-console` via `CACHE_URL`.

## Run & test
```bash
pip install -r services/cache/requirements.txt pytest httpx2 ruff==0.16.0
pip install fakeredis==2.37.0
ruff check services/cache
cd services/cache && python -m pytest tests -v
```
The tests swap `main.r` for `fakeredis.FakeRedis(decode_responses=True)` after import. They cover health, the L1 round-trip, the L5 403 and the legacy alias. `requirements-dev.txt` pins `fakeredis==2.23.2`, but CI installs 2.37.0.

Run it alone:
```bash
docker compose up -d redis
cd services/cache && REDIS_HOST=localhost uvicorn app.main:app --port 8005
curl -s -X POST http://localhost:8005/cache/L2/foo -H 'content-type: application/json' -d '{"answer":42}'
curl -s http://localhost:8005/cache/L2/foo
curl -s -X POST "http://localhost:8005/cache/L5/bar?l5_policy_allowed=true" -H 'content-type: application/json' -d '{"x":1}'
```

## Changing it
- **Route order matters.** The FastAPI paths `/cache/{layer}/{key}` and `/cache/{key}` are distinguished by segment count, so a key containing `/` will not reach the legacy route.
- Keep the legacy `/cache/{key}` alias. It is explicitly kept for v0.0.1 callers.
- Docs versus code: `Microservices-Architecture-v2.md` (end of §4) says a denied L5 returns `{"cache_hit": false, "reason": "L5_policy_denied"}`, but the code returns HTTP 403. Pick one deliberately and update the other.
- If you add a layer, update `CACHE_LAYERS`, the `/health` `layers` list and the docs table.
- Tests patch the module-level `r`. Keep Redis access through `main.r`, and do not create new clients inside handlers.

## Related skills
- aepx-svc-memory (the next tier in the reuse order)
- aepx-svc-discovery (also Redis-backed, and uses fakeredis in CI)
- aepx-svc-gateway
- aepx-svc-cost-optimiser (decides which layer to check)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
