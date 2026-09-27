---
name: aepx-conn-devtools
description: Developer-tools connector service (connectors/devtools) with 11 connectors including live GitHub, GitLab and Docker Hub adapters plus Jira, Jenkins, SonarQube stubs. Use when invoking or testing a devtools connector, or promoting another devtools stub to a real adapter.
---

# Developer tools connectors (`connectors/devtools`)

## Role

Source control, CI/CD, artefact registries and IaC. AIA-R0 / 40 for SCM and trackers; AIA-R1 / 50 for `jenkins`, `circleci`, `artifactory` and `terraform-cloud`. Nothing is policy-denied by default, and a fresh agent (trust 50) can reach every connector.

Risk classes in this category: AIA-R0 x7, AIA-R1 x4.

## Where

- Code: `connectors/devtools/app/main.py` (routes) and `connectors/devtools/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/devtools/tests/test_health.py`. Deps: `connectors/devtools/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-devtools`**, host port **8023** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose (so `GITHUB_TOKEN` and `GITLAB_TOKEN` are unset by default and both adapters run unauthenticated).
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "devtools")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-devtools:8000`, overridable with `CONNECTOR_URL_DEVTOOLS` on the connector-bus.

## Connectors

11 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `github` | REST, GraphQL | AIA-R0 | 40 | specialized |
| `gitlab` | REST, GraphQL | AIA-R0 | 40 | specialized |
| `jira` | REST | AIA-R0 | 40 | stub |
| `azure-devops` | REST | AIA-R0 | 40 | stub |
| `bitbucket` | REST | AIA-R0 | 40 | stub |
| `jenkins` | REST | AIA-R1 | 50 | stub |
| `circleci` | REST | AIA-R1 | 50 | stub |
| `sonarqube` | REST | AIA-R0 | 40 | stub |
| `artifactory` | REST | AIA-R1 | 50 | stub |
| `dockerhub` | REST | AIA-R0 | 40 | specialized |
| `terraform-cloud` | REST | AIA-R1 | 50 | stub |

## Specialized adapters

All three make real HTTPS calls with a 10s timeout. On any exception they return a `specialized_degraded` fallback (`confidence: 0.3`, `result: "[fallback: ... unreachable (<ExcType>) for '<target>']"`), never a 5xx.

### `github`: `GitHubAdapter`
- Ops: `list_open_issues`. Anything else returns `{"op", "error": "unsupported operation in this adapter"}`.
- Payload: `repo` (default `"octocat/Hello-World"`).
- Env: `GITHUB_TOKEN`, optional. When set it sends `Authorization: Bearer`; when unset it runs unauthenticated. The docstring gives 60 req/hr unauthenticated and 5000/hr with a token.
- Calls `GET https://api.github.com/repos/{repo}/issues?state=open&per_page=5` and drops pull requests. The result is a list of `{number, title, state}`.

### `dockerhub`: `DockerHubAdapter`
- Ops: `repo` returns `{name, namespace, pull_count, star_count, description, last_updated}`. `tags` returns the 10 most recent tag names. Anything else returns `unsupported operation (use 'repo' or 'tags')`.
- Payload: `repo` (default `"library/python"`). A bare name becomes `library/<name>`.
- Env: none. Uses the public `https://hub.docker.com/v2` API without auth.

### `gitlab`: `GitLabAdapter`
- Ops: `project` returns `{name, star_count, forks_count, description, last_activity_at}`. `list_issues` returns up to 5 opened issues as `{iid, title, state}`. Anything else returns `unsupported operation (use 'project' or 'list_issues')`.
- Payload: `project` (default `"gitlab-org/gitlab"`), URL-encoded as `namespace%2Fpath`.
- Env: `GITLAB_TOKEN`, optional, sent as the `PRIVATE-TOKEN` header. Public projects work without it.

The other 8 connectors use `StubAdapter`. Note that docs/Connector-Catalogue.md still lists `gitlab` and `dockerhub` as `stub`; `catalogue.json` says `specialized`.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-devtools", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `devtools`, otherwise 404 `connector '<name>' is not registered in category 'devtools'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/devtools/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/devtools
cd connectors/devtools && python -m pytest tests -v
```

Tests: health, 11 catalogue entries, stub dispatch (`terraform-cloud`), unknown 404, and for each of github/dockerhub/gitlab a no-network fallback plus a mocked-`httpx.get` live response. There is also a bare-name and unsupported-op check. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8023/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/github","payload":{"op":"list_open_issues","repo":"octocat/Hello-World"}}'
```

Docker Hub: `"receiver":"aepx://connector/dockerhub","payload":{"op":"tags","repo":"redis"}`.

## Adding a real adapter here

- Copy the `GitLabAdapter` shape: an optional token from env, a `_headers()` helper, op dispatch inside a single `try` with a degraded fallback, and a 10s timeout.
- Prefer targets that work unauthenticated for public data (github, dockerhub and gitlab all do), so the adapter is useful with zero config.
- Tests must monkeypatch `httpx.get`/`httpx.post`. CI has no network guarantees.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
