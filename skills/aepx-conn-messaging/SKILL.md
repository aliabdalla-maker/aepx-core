---
name: aepx-conn-messaging
description: Messaging connector service (connectors/messaging) with 8 broker connectors (Kafka, NATS, RabbitMQ, MQTT, AMQP, Pulsar, AWS SQS, Azure Service Bus). Use when invoking or testing a messaging connector or building its first real adapter.
---

# Messaging connectors (`connectors/messaging`)

## Role

Message brokers and queues. AIA-R0 / 40 for `nats`, `rabbitmq`, `mqtt`, `amqp` and `pulsar`; AIA-R1 / 50 for `kafka`, `aws-sqs` and `azure-servicebus`. All are allowed by the default policy and reachable by a fresh agent. These are external brokers. The platform's own internal Kafka (the audit bus) is separate and is not reached through this connector.

Risk classes in this category: AIA-R0 x5, AIA-R1 x3.

## Where

- Code: `connectors/messaging/app/main.py` (routes) and `connectors/messaging/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/messaging/tests/test_health.py`. Deps: `connectors/messaging/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-messaging`**, host port **8026** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "messaging")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-messaging:8000`, overridable with `CONNECTOR_URL_MESSAGING` on the connector-bus.

## Connectors

8 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `kafka` | Kafka | AIA-R1 | 50 | stub |
| `nats` | NATS | AIA-R0 | 40 | stub |
| `rabbitmq` | AMQP | AIA-R0 | 40 | stub |
| `mqtt` | MQTT | AIA-R0 | 40 | stub |
| `amqp` | AMQP | AIA-R0 | 40 | stub |
| `pulsar` | Pulsar | AIA-R0 | 40 | stub |
| `aws-sqs` | REST | AIA-R1 | 50 | stub |
| `azure-servicebus` | AMQP, REST | AIA-R1 | 50 | stub |

## Specialized adapters

All 8 connectors are stubs: `SPECIALIZED = {}` in `connectors/messaging/app/adapters.py`. `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-messaging", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `messaging`, otherwise 404 `connector '<name>' is not registered in category 'messaging'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/messaging/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/messaging
cd connectors/messaging && python -m pytest tests -v
```

Tests: health, 8 catalogue entries, stub dispatch (`azure-servicebus`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8026/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/nats","payload":{"op":"publish"}}'
```

Returns the canonical stub.

## Adding a real adapter here

- This is the first specialized adapter here. Add the client library pinned in `connectors/messaging/requirements.txt`. Only the connector-bus pins `kafka-python==2.0.2` today; this service does not.
- Take broker URL/credentials from env and add a compose `environment:` block for `connector-messaging`. Degrade to `specialized_degraded` if the broker is unreachable, and mock the client in tests.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
