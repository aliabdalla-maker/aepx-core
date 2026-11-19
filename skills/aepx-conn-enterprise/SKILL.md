---
name: aepx-conn-enterprise
description: Enterprise connector service (connectors/enterprise) with 14 ERP/CRM/HR/finance connectors such as SAP, Salesforce, Workday and ServiceNow. Use when invoking, testing or upgrading an enterprise connector, or debugging its routing through the bus.
---

# Enterprise connectors (`connectors/enterprise`)

## Role

ERP, CRM, HR and finance systems (SAP, Salesforce, Dynamics 365, Workday, NetSuite ...). The category is split between AIA-R1 (CRM/ticketing, min trust 50) and AIA-R2 (ERP/HR/finance, min trust 60). Both are allowed under the seed `max_risk_level: S2` policy, so nothing here is policy-denied by default. SOA-Architecture.md §4 notes that HR data (Workday) defaults to AIA-R2+ and needs at least Silver assurance before go-live. A never-seen agent has trust score 50 (Trust's default), so a connector with `min_trust_score` above 50 returns 403 `trust score 50 below required ...` until the agent's trust is higher.

Risk classes in this category: AIA-R1 x4, AIA-R2 x10.

## Where

- Code: `connectors/enterprise/app/main.py` (routes) and `connectors/enterprise/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/enterprise/tests/test_health.py`. Deps: `connectors/enterprise/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-enterprise`**, host port **8021** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. No `environment:` block in compose.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "enterprise")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-enterprise:8000`, overridable with `CONNECTOR_URL_ENTERPRISE` on the connector-bus.

## Connectors

14 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `sap` | SOAP, REST | AIA-R2 | 60 | stub |
| `salesforce` | SOAP, REST | AIA-R1 | 50 | specialized |
| `dynamics365` | REST | AIA-R2 | 60 | stub |
| `oracle-erp` | SOAP, REST | AIA-R2 | 60 | stub |
| `workday` | SOAP, REST | AIA-R2 | 60 | stub |
| `servicenow` | REST | AIA-R1 | 50 | stub |
| `bamboohr` | REST | AIA-R2 | 60 | stub |
| `successfactors` | REST | AIA-R2 | 60 | stub |
| `xero` | REST | AIA-R2 | 60 | stub |
| `quickbooks` | REST | AIA-R2 | 60 | stub |
| `netsuite` | SOAP, REST | AIA-R2 | 60 | stub |
| `hubspot` | REST | AIA-R1 | 50 | stub |
| `sage` | REST | AIA-R2 | 60 | stub |
| `zoho-crm` | REST | AIA-R1 | 50 | stub |

## Specialized adapters

### `salesforce`: `SalesforceAdapter` (catalogue maturity `specialized`)

- Ops: `lookup_contact` only. Any other op returns `{"op": op, "error": "unsupported operation in this adapter"}`.
- Payload fields: `op`. No other field is read.
- Env vars/credentials: none. It makes no network call and returns a fixed fixture contact (`id`, `name`, `email`) with `source: "connector:salesforce"`, `confidence: 0.95` and `maturity: "specialized"`. The code comment says to swap it for a real `simple_salesforce` call once credentials exist.
- Without credentials the behaviour is the same, because it never uses any.

All other 13 connectors are served by `StubAdapter`.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-enterprise", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `enterprise`, otherwise 404 `connector '<name>' is not registered in category 'enterprise'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/enterprise/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/enterprise
cd connectors/enterprise && python -m pytest tests -v
```

Tests: health, 14 catalogue entries, stub dispatch (`zoho-crm`), unknown connector 404. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8021/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/salesforce","payload":{"op":"lookup_contact"}}'
```

Expected: the fixture contact. A stub, e.g. `zoho-crm` (R1/50), works the same way. R2 connectors such as `sap` need trust ≥ 60.

## Adding a real adapter here

- The first real adapter is expected to replace `SalesforceAdapter`'s fixture with a live client (the code comment names `simple_salesforce`). Pin the library in `connectors/enterprise/requirements.txt` and read credentials from env vars. There is no `environment:` block for `connector-enterprise` in compose yet, so add one.
- Keep the fixture as a no-credentials fallback so the existing test path still passes without network.
- SOA-Architecture.md §5: validate the pattern on Salesforce before building SAP/Dynamics/Oracle/Workday/ServiceNow.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
