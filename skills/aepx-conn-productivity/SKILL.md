---
name: aepx-conn-productivity
description: Productivity connector service (connectors/productivity) with 11 collaboration connectors (Slack, Teams, Google Workspace, M365, Notion, Confluence, Asana). Use when posting to Slack via the bus, testing a productivity connector, or adding a real adapter for one.
---

# Productivity connectors (`connectors/productivity`)

## Role

Collaboration and office suites. Mostly AIA-R0 / min trust 40; `google-workspace`, `microsoft365` and `dropbox` are AIA-R1 / 50. All are allowed by the default policy, and a fresh agent (trust 50) can reach every connector in the category.

Risk classes in this category: AIA-R0 x8, AIA-R1 x3.

## Where

- Code: `connectors/productivity/app/main.py` (routes) and `connectors/productivity/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/productivity/tests/test_health.py`. Deps: `connectors/productivity/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-productivity`**, host port **8024** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. Compose passes `SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN:-}` from `.env` (listed in `.env.example`); it is empty by default, so the adapter degrades.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "productivity")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-productivity:8000`, overridable with `CONNECTOR_URL_PRODUCTIVITY` on the connector-bus.

## Connectors

11 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `google-workspace` | REST | AIA-R1 | 50 | stub |
| `microsoft365` | REST | AIA-R1 | 50 | stub |
| `slack` | REST | AIA-R0 | 40 | specialized |
| `teams` | REST | AIA-R0 | 40 | stub |
| `zoom` | REST | AIA-R0 | 40 | stub |
| `notion` | REST | AIA-R0 | 40 | stub |
| `confluence` | REST | AIA-R0 | 40 | stub |
| `trello` | REST | AIA-R0 | 40 | stub |
| `asana` | REST | AIA-R0 | 40 | stub |
| `monday` | REST, GraphQL | AIA-R0 | 40 | stub |
| `dropbox` | REST | AIA-R1 | 50 | stub |

## Specialized adapters

### `slack`: `SlackAdapter` (catalogue maturity `specialized`)

- Ops: `post_message` only. Any other op returns `{"op": op, "error": "unsupported operation in this adapter"}`.
- Payload fields: `channel` (default `"#general"`), `text` (default `""`).
- Env var: `SLACK_BOT_TOKEN`, read once at construction (`self.token`). The docstring says to store it in Vault/env.
- With a token it calls `POST https://slack.com/api/chat.postMessage` with a `Bearer` header and a 10s timeout. On `ok: true` it returns `result: {channel, posted: true, ts}` with `maturity: "specialized"` and `confidence: 0.99`.
- Without a token it returns `result: "[stub: no SLACK_BOT_TOKEN configured — would post to '<channel>']"` with `maturity: "specialized_degraded"` and `confidence: 0.5`. It does not call Slack.
- On an API/network error, or Slack returning `ok: false`, it returns `[fallback: Slack API call failed (<ExcType>) for '<channel>']` with `specialized_degraded` and `confidence: 0.3`.

The other 10 connectors use `StubAdapter`.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-productivity", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `productivity`, otherwise 404 `connector '<name>' is not registered in category 'productivity'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/productivity/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/productivity
cd connectors/productivity && python -m pytest tests -v
```

Tests: health, 11 catalogue entries, stub dispatch (`dropbox`), unknown 404, Slack without token (degraded), Slack with a fake token and mocked `httpx.post` (posted). The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8024/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/slack","payload":{"op":"post_message","channel":"#general","text":"hello"}}'
```

Without `SLACK_BOT_TOKEN` this returns the `specialized_degraded` stub message.

## Adding a real adapter here

- Follow `SlackAdapter`: read the token from env in `__init__`, return `specialized_degraded` when it is absent, and wrap the live call in `try/except` with a `specialized_degraded` fallback.
- Add the env var to `.env.example` and to a new `environment:` block on `connector-productivity` in `docker-compose.yml`. None exists today.
- Test by monkeypatching the adapter's `token` attribute and `httpx.post`, as `test_slack_adapter_*` does.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
