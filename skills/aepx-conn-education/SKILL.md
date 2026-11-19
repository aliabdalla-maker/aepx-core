---
name: aepx-conn-education
description: Education connector service (connectors/education) with 4 LMS connectors (Moodle, Canvas, Blackboard, Google Classroom), all AIA-R2 / min trust 60 and all stubs. Use when invoking or testing an education connector or building its first real adapter.
---

# Education connectors (`connectors/education`)

## Role

Learning-management systems. All 4 are AIA-R2 / min trust 60. They are allowed by the default S2 policy, but a never-seen agent has trust score 50 (Trust's default), so a connector with `min_trust_score` above 50 returns 403 `trust score 50 below required ...` until the agent's trust is higher. SOA-Architecture.md §3.2 lists Government/Education as reference design only.

Risk classes in this category: AIA-R2 x4.

## Where

- Code: `connectors/education/app/main.py` (routes) and `connectors/education/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/education/tests/test_health.py`. Deps: `connectors/education/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-education`**, host port **8030** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "education")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-education:8000`, overridable with `CONNECTOR_URL_EDUCATION` on the connector-bus.

## Connectors

4 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `moodle` | REST | AIA-R2 | 60 | stub |
| `canvas` | REST, GraphQL | AIA-R2 | 60 | stub |
| `blackboard` | REST | AIA-R2 | 60 | stub |
| `google-classroom` | REST | AIA-R2 | 60 | stub |

## Specialized adapters

All 4 connectors are stubs: `SPECIALIZED = {}` in `connectors/education/app/adapters.py`. `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-education", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `education`, otherwise 404 `connector '<name>' is not registered in category 'education'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/education/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/education
cd connectors/education && python -m pytest tests -v
```

Tests: health, 4 catalogue entries, stub dispatch (`google-classroom`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8030/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/moodle","payload":{"op":"list_courses"}}'
```

Returns the stub once the calling agent's trust ≥ 60; a brand-new agent gets 403 on trust. For local stub debugging only, call `localhost:8030/connector/execute` directly (bypasses governance).

## Adding a real adapter here

- This is the first specialized adapter here. Moodle and Canvas both expose REST (and Canvas GraphQL, per the catalogue). Read the site URL and token from env, add a compose `environment:` block for `connector-education`, and degrade when unset.
- Student data is involved and the class is AIA-R2, so keep ops read-only until governance has reviewed them.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
