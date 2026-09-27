---
name: aepx-conn-industrial
description: Industrial connector service (connectors/industrial) with 8 OT/ICS connectors (OPC-UA, Modbus, BACnet, SCADA, PLC, Sparkplug, PROFINET, EtherNet/IP), all AIA-R3 and policy-denied by default. Use when working on industrial connectors or explaining why they return 403.
---

# Industrial connectors (`connectors/industrial`)

## Role

Operational-technology protocols with physical-world side effects. **All 8 are AIA-R3 / min trust 70.** AIA-R3 connectors are **denied by default**: Governance maps AIA-R3 to S3, which is above the seed `max_risk_level: S2`, so the bus returns 403 `policy denies risk level AIA-R3 ...` before the category service is reached. The bus test `test_route_denies_high_risk_connector_by_policy` asserts this for `opcua`. SOA-Architecture.md keeps the category as backlog/reference design until a pilot names a real OPC-UA target. §3.2 also calls for a mandatory Safety Engine pre-check, which is not implemented in the bus or this service today.

Risk classes in this category: AIA-R3 x8.

## Where

- Code: `connectors/industrial/app/main.py` (routes) and `connectors/industrial/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/industrial/tests/test_health.py`. Deps: `connectors/industrial/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-industrial`**, host port **8027** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "industrial")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-industrial:8000`, overridable with `CONNECTOR_URL_INDUSTRIAL` on the connector-bus.

## Connectors

8 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `opcua` | OPC-UA | AIA-R3 | 70 | stub |
| `modbus` | Modbus | AIA-R3 | 70 | stub |
| `bacnet` | BACnet | AIA-R3 | 70 | stub |
| `scada` | OPC-UA, Custom | AIA-R3 | 70 | stub |
| `plc` | Modbus, Custom | AIA-R3 | 70 | stub |
| `sparkplug` | MQTT-Sparkplug | AIA-R3 | 70 | stub |
| `profinet` | PROFINET | AIA-R3 | 70 | stub |
| `ethernet-ip` | EtherNet/IP | AIA-R3 | 70 | stub |

## Specialized adapters

All 8 connectors are stubs: `SPECIALIZED = {}` in `connectors/industrial/app/adapters.py`. `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-industrial", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `industrial`, otherwise 404 `connector '<name>' is not registered in category 'industrial'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/industrial/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/industrial
cd connectors/industrial && python -m pytest tests -v
```

Tests: health, 8 catalogue entries, stub dispatch (`ethernet-ip`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8027/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/opcua","payload":{"op":"read_tag"}}'
```

Expected: **403** `policy denies risk level AIA-R3 for connector 'opcua'`, with a `connector.failed` audit event. To exercise the stub itself in local debugging only, call the service directly and bypass governance: `curl -s -X POST localhost:8027/connector/execute -H 'Content-Type: application/json' -d '{"sender":"aepx://agent/x","receiver":"aepx://connector/ethernet-ip","payload":{"op":"ping"}}'`.

## Adding a real adapter here

- Don't build one without a real pilot target (SOA-Architecture.md §5 backlog). Even a working adapter stays unreachable via the bus while the policy ceiling is S2. Raising it is a governance decision for the user, not a code change to make here (see `aepx-governance-policy`).
- Any real adapter should default to read-only ops and degrade cleanly. The Safety pre-check called for in §3.2 would need to be designed first.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
