---
name: aepx-connector-bus
description: The AEP-X Connector Bus (connector-bus/), the SOA mediation layer that trust-checks, policy-checks, circuit-breaks, routes and audits every connector call. Use when changing /bus/route, debugging 403/404/503 from the bus, or tracing how a connector name reaches its category service.
---

# AEP-X Connector Bus (`connector-bus/`)

## Role

The single mediation point between the microservices core and the 11 category connector services (docs/SOA-Architecture.md §3). Every connector call enters as an RFC-0001 envelope on `POST /bus/route` and is centrally orchestrated: trust check, governance policy check, circuit breaker, forward to the owning category service, Kafka audit. No connector service is meant to be called directly and no connector calls another (SOA-Architecture.md §3.1 rule 5).

## Where

- Code: `connector-bus/app/main.py` (single module, FastAPI `version="0.2.0"`); tests: `connector-bus/tests/test_health.py`.
- Compose service `connector-bus`, host port **8020** -> container 8000.
- Compose env: `TRUST_URL`, `GOVERNANCE_URL`, `BRAIN_URL`; mounts `./connectors/catalogue.json:/app/catalogue.json:ro`.
- `depends_on: [trust, governance, brain]`. The compose comment says to bring up `trust governance` first in a fresh environment (SOA-Architecture.md §5). It does not depend on `kafka` and compose does not set `KAFKA_BOOTSTRAP`, so the code default `kafka:9092` applies.
- Callers configured with `CONNECTOR_BUS_URL=http://connector-bus:8000`: gateway, console, oracle-bridge and others in `docker-compose.yml`.

## Request flow (`POST /bus/route`)

1. **Resolve connector.** Name = last path segment of `receiver` (`aepx://connector/github` -> `github`). If it is not in the catalogue-loaded table -> **404** `unknown connector '<name>' — not in catalogue`. `agent_id` = last path segment of `sender`.
2. **Trust check (Law 2).** `GET {TRUST_URL}/trust/{agent_id}`, reading `trust_score` (missing -> 0). If `trust_score < min_trust_score` for that connector -> audit `denied/trust_below_threshold` -> **403**. A never-seen agent gets Trust's default score of 50, so connectors with `min_trust_score` 60 or 70 reject a fresh agent.
3. **Policy check.** `POST {GOVERNANCE_URL}/policy/evaluate?risk_level=<ai_risk_class>`. A non-200 response is treated as `{"allowed": false}`. If not allowed -> audit `denied/policy_denied` -> **403** `policy denies risk level ...`. Governance maps `AIA-Rn` to `Sn` and compares against `max_risk_level` (seed `S2`, or an on-chain `AEPXPolicyRegistry` value when configured). With the defaults, AIA-R0..R2 pass and AIA-R3 (all industrial, 3 of 4 government connectors) is denied.
4. **Circuit breaker.** `GET {BRAIN_URL}/brain/circuit/{name}`. If `allowed` is false -> audit `denied/circuit_open` -> **503** `connector '<name>' is circuit-broken (reliability ...)`. Any other exception (Brain down, bad JSON) is **fail-open**: the call proceeds.
5. **Forward.** `POST {base_url}/connector/execute` with the whole envelope (`envelope.model_dump()`), timeout **30s**. Trust/policy/circuit calls share one `httpx.AsyncClient` with a **3s** timeout.
6. **Audit + trust nudge.** Audit `invoked`, then best-effort `POST {TRUST_URL}/trust/{agent_id}/adjust` with `{"component": "behaviour", "delta": 1}` (errors swallowed).
7. **Response** `200`: `{connector, category, ai_risk_class, maturity, trust_score_at_call_time, response}`, where `response` is the category service's JSON body.

Failure behaviour to know:
- Trust or Governance unreachable, or the forward raising (connection error, timeout, non-JSON body): the exception is not caught -> FastAPI 500, and no `invoked` audit is sent.
- The forward's HTTP status is not checked: a 404 from the category service (e.g. connector not registered there) still comes back as a bus 200 with `response: {"detail": ...}` and an `invoked` audit.
- Audit (`_audit`) publishes to Kafka topic `connector.invoked` for `invoked` and `connector.failed` for every denial. The event carries `id, agent_id, connector, outcome, reason, trust_score, ai_risk_class, ts`. The producer is lazy and retried per call (`_get_producer`); if `kafka-python` is missing or the broker is unreachable, audit is silently skipped.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-bus", connector_count, categories, connectors}` (sorted names). Count is 107 across 11 categories with the repo catalogue. |
| POST | `/bus/route` | Body `Envelope`: `version` ("1.0"), `sender`, `receiver`, `messageType` ("request"), `payload` (dict, required), `metadata` ({}). Flow above. Codes: 200, 403, 404, 503, 500 on dependency errors. |

## Configuration

| Env var | Default in code | Purpose |
|---|---|---|
| `TRUST_URL` | `http://trust:8000` | Trust Authority (`/trust/{id}`, `/trust/{id}/adjust`) |
| `GOVERNANCE_URL` | `http://governance:8000` | `/policy/evaluate` |
| `BRAIN_URL` | `http://brain:8000` | `/brain/circuit/{name}` |
| `CATALOGUE_PATH` | `/app/catalogue.json` | Routing table source |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Audit producer |
| `CONNECTOR_URL_<CATEGORY>` | `http://connector-<category>:8000` | Per-category base URL override (e.g. `CONNECTOR_URL_BLOCKCHAIN`) |

## Routing

`_load_connectors()` reads `catalogue.json` once at import. For each entry it stores `category`, `base_url`, `ai_risk_class`, `min_trust_score` and `maturity` (default `stub`). `base_url` = `os.getenv(f"CONNECTOR_URL_{category.upper()}", f"http://connector-{category}:8000")`. The table is data, not code: a new catalogue row is routable once the bus restarts. If the catalogue can't be read, the table is empty and every route returns 404. For a local/hybrid run, set e.g. `CONNECTOR_URL_DEVTOOLS=http://localhost:8023`.

## Run & test

CI (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connector-bus/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connector-bus
cd connector-bus && python -m pytest tests -v
```

The tests set `CATALOGUE_PATH` to `../connectors/catalogue.json` and monkeypatch `httpx.AsyncClient`. They cover: 107 connectors / 11 categories, allow (salesforce) with one behaviour adjust, stub routing (pinecone), policy deny for AIA-R3 (opcua), circuit-open 503, Brain-down fail-open, 30s forward timeout guard, producer returns None without Kafka, and unknown-connector 404. `ruff.toml` pins rules `E4, E7, E9, F`.

With the stack up (`docker compose up -d trust governance brain connector-bus connector-devtools`):

```bash
curl -s localhost:8020/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/github","payload":{"op":"list_open_issues","repo":"octocat/Hello-World"}}'
```

CLI equivalent: `aepx invoke github --payload '{"op":"list_open_issues"}'` (default sender `aepx://agent/cli`).

## Changing it

- Keep the order trust -> policy -> circuit -> forward. Every denial must `_audit(...)` before raising. The tests and SOA-Architecture.md §6 Definition of Done depend on it.
- Keep Brain fail-open and the 30s forward override. Both are regression-tested.
- Governance's `max_risk_level` lives in `services/governance`, not here. Changing what is allowed is a governance decision (see `aepx-governance-policy`).
- New fields in the response or audit event need matching test updates. Consumers include the console, gateway and oracle-bridge.
- Keep `requirements.txt` pins in step with the connector services (fastapi 0.111.0, pydantic 2.7.1, httpx 0.27.0; plus kafka-python 2.0.2 here only).

## Related skills

- `aepx-conn-<category>`: the 11 category services the bus forwards to.
- `aepx-connector-adapter`: add a catalogue row or real adapter.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the policy the bus enforces.
- `aepx-run-stack`: bringing the stack up.
