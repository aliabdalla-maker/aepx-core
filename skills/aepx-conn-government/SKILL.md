---
name: aepx-conn-government
description: Government connector service (connectors/government) with 4 public-sector connectors (digital identity, citizen services, notify, pay). Three are AIA-R3 and policy-denied by default; gov-notify is AIA-R2. Use when working on government connectors or explaining their 403s.
---

# Government connectors (`connectors/government`)

## Role

Public-sector digital services. `gov-digital-identity`, `gov-citizen-services` and `gov-pay` are **AIA-R3 / min trust 70**. AIA-R3 connectors are **denied by default**: Governance maps AIA-R3 to S3, which is above the seed `max_risk_level: S2`, so the bus returns 403 `policy denies risk level AIA-R3 ...` before the category service is reached. `gov-notify` is AIA-R2 / 60, so it passes policy but needs trust ≥ 60 (a fresh agent has 50). SOA-Architecture.md §3.2 treats Government/Education as reference design only, with no named concrete system to integrate against.

Risk classes in this category: AIA-R2 x1, AIA-R3 x3.

## Where

- Code: `connectors/government/app/main.py` (routes) and `connectors/government/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/government/tests/test_health.py`. Deps: `connectors/government/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-government`**, host port **8029** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "government")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-government:8000`, overridable with `CONNECTOR_URL_GOVERNMENT` on the connector-bus.

## Connectors

4 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `gov-digital-identity` | REST, OIDC | AIA-R3 | 70 | stub |
| `gov-citizen-services` | REST | AIA-R3 | 70 | stub |
| `gov-notify` | REST | AIA-R2 | 60 | stub |
| `gov-pay` | REST | AIA-R3 | 70 | stub |

## Specialized adapters

All 4 connectors are stubs: `SPECIALIZED = {}` in `connectors/government/app/adapters.py`. `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-government", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `government`, otherwise 404 `connector '<name>' is not registered in category 'government'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/government/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/government
cd connectors/government && python -m pytest tests -v
```

Tests: health, 4 catalogue entries, stub dispatch (`gov-pay`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8029/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/gov-notify","payload":{"op":"send"}}'
```

Returns the stub only if the agent's trust ≥ 60; otherwise 403 on trust. `gov-pay` and the other R3 connectors return 403 on policy. For local debugging of the stub only, call `localhost:8029/connector/execute` directly (bypasses governance).

## Adding a real adapter here

- There is no concrete target system yet (reference design only). Don't invent one.
- The R3 connectors stay unreachable through the bus under the S2 ceiling. Changing that is a governance decision (`aepx-governance-policy`), not part of adding an adapter.
- Any identity or payment adapter handles citizen data. Read credentials from env/Vault only and degrade cleanly when unset.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
