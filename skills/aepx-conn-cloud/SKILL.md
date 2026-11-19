---
name: aepx-conn-cloud
description: Cloud connector service (connectors/cloud) with 10 AWS, Azure, GCP and Cloudflare connectors (object storage, serverless, Kubernetes). Use when invoking or testing a cloud connector or building its first real adapter.
---

# Cloud connectors (`connectors/cloud`)

## Role

Hyperscaler storage, compute and edge. AIA-R1 / 50 for storage, functions, Cloud Run and Cloudflare; AIA-R2 / 60 for the managed Kubernetes connectors `aws-eks`, `azure-aks` and `gcp-gke`. All are allowed by the default policy. A never-seen agent has trust score 50 (Trust's default), so a connector with `min_trust_score` above 50 returns 403 `trust score 50 below required ...` until the agent's trust is higher.

Risk classes in this category: AIA-R1 x7, AIA-R2 x3.

## Where

- Code: `connectors/cloud/app/main.py` (routes) and `connectors/cloud/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/cloud/tests/test_health.py`. Deps: `connectors/cloud/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-cloud`**, host port **8028** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "cloud")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-cloud:8000`, overridable with `CONNECTOR_URL_CLOUD` on the connector-bus.

## Connectors

10 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `aws-s3` | REST | AIA-R1 | 50 | stub |
| `aws-lambda` | REST | AIA-R1 | 50 | stub |
| `aws-eks` | REST | AIA-R2 | 60 | stub |
| `azure-blob` | REST | AIA-R1 | 50 | stub |
| `azure-aks` | REST | AIA-R2 | 60 | stub |
| `azure-functions` | REST | AIA-R1 | 50 | stub |
| `gcp-storage` | REST | AIA-R1 | 50 | stub |
| `gcp-gke` | REST | AIA-R2 | 60 | stub |
| `gcp-cloudrun` | REST | AIA-R1 | 50 | stub |
| `cloudflare` | REST | AIA-R1 | 50 | stub |

## Specialized adapters

All 10 connectors are stubs: `SPECIALIZED = {}` in `connectors/cloud/app/adapters.py`. `StubAdapter(name, category).execute(payload)` returns `{op, result: "[stub response from connector '<name>' (<category>) for op '<op>']", source: "connector:<name>", confidence: 0.5, maturity: "stub"}`; `op` defaults to `"default"`. It makes no network call and reads no env vars.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-cloud", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `cloud`, otherwise 404 `connector '<name>' is not registered in category 'cloud'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/cloud/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/cloud
cd connectors/cloud && python -m pytest tests -v
```

Tests: health, 10 catalogue entries, stub dispatch (`cloudflare`), unknown 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8028/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/aws-s3","payload":{"op":"list_buckets"}}'
```

Returns the canonical stub. `aws-eks`, `azure-aks` and `gcp-gke` need trust ≥ 60.

## Adding a real adapter here

- This is the first specialized adapter here. Pin the SDK in `connectors/cloud/requirements.txt`, read cloud credentials only from env/Vault (never commit them), add a compose `environment:` block for `connector-cloud`, and degrade when unset.
- Start with read-only ops. The Kubernetes connectors are AIA-R2, so keep writes out until governance has reviewed them.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
