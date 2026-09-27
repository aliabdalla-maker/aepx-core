---
name: aepx-svc-marketplace
description: Marketplace Engine for AEP-X, holding draft asset listings behind a governed publish gate (Trust >= 60 AND a Governance policy allow, fail-closed). Use when working on, debugging, calling or extending the marketplace service in aepx-core.
---

# Marketplace Engine service (`services/marketplace`)

## Role
This service publishes and lets users discover platform assets. Its core is the **governed publish gate**. A listing moves from `draft` to `published` only if both of these hold at publish time:
- the publisher's Trust score is at least the threshold (Law 2)
- Governance policy allows the listing's risk level (the docstring cites Law 6/8)

The gate **fails closed**. If Trust or Governance cannot be reached, nothing is published, unlike the platform's read paths, which degrade gracefully. It is a reference implementation and keeps its store in memory.

## Where
- Code: `services/marketplace/app/main.py`.
- Compose service `marketplace`, host port **8016** -> container 8000.
- Environment: `TRUST_URL=http://trust:8000`, `GOVERNANCE_URL=http://governance:8000`.
- `depends_on: [trust, governance]`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"marketplace", listings: <count>}` |
| POST | `/marketplace/listings` | Create a draft listing | `ListingIn`: `{name, asset_type="agent", publisher="aepx://agent/anonymous", risk_level="S2", description=""}`. Returns `{id, name, asset_type, publisher, risk_level, description, status:"draft", created_at}`. An invalid `asset_type` returns 400 |
| GET | `/marketplace/listings?status=` | List listings, with an optional status filter | A list of listing dicts |
| GET | `/marketplace/listings/{listing_id}` | Fetch one listing | A listing dict, or 404 `"listing not found"` |
| POST | `/marketplace/listings/{listing_id}/publish` | Run the publish gate | **Pass:** the listing with `status:"published"`, `published_at` and `publish_trust_score`. **Deny:** the listing with `status:"review"`, `last_denied_reason`, `published:false` and `reason`. An unknown id returns 404 |

- **Asset types:** `ASSET_TYPES = {agent, workflow, plugin, knowledge_pack, model}`.
- **Gate order:**
  1. Trust. If it is unreachable, the reason is `trust check unavailable (...) — fail-closed`. If the score is too low, the reason is `publisher trust X < required N`.
  2. Policy. If it is unreachable, the reason is `policy check unavailable (...) — fail-closed`. If it denies, the reason is `policy denied risk level ...`.
- Deny reasons are returned with HTTP 200, not as an error status.

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `TRUST_URL` | `http://trust:8000` | The service calls `GET {TRUST_URL}/trust/{publisher}` and reads `trust_score` |
| `GOVERNANCE_URL` | `http://governance:8000` | The service calls `POST {GOVERNANCE_URL}/policy/evaluate?risk_level=...` and reads `allowed` |
| `MARKETPLACE_MIN_TRUST` | `60` | Minimum publisher trust needed to publish |

## Data & dependencies
- **Storage:** the in-memory `_LISTINGS` dict. Listings are lost on restart. There is no SQL schema for it in `schemas/sql/`.
- **Calls:** Trust and Governance, each with a 5 s timeout and `raise_for_status()`. Any exception or non-2xx response counts as unavailable, so the gate fails closed.
- **Kafka:** none. It neither publishes nor consumes.
  - The docstring says the durable record is Governance's audit trail. However, Governance only audits Kafka topics, and `/policy/evaluate` writes no audit row.
  - So publish decisions are **not** audited today. Add a Kafka event, and a matching Governance `_CONSUMED_TOPICS` entry, if you need them audited.
- **Monitoring:** not in Gateway's `SERVICES` health aggregate (even though compose sets `MARKETPLACE_URL` on the gateway), and not in the Brain's `MONITORED_SERVICES`. `platform/aepx-console` lists it.

## Run & test
```bash
pip install -r services/marketplace/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/marketplace
cd services/marketplace && python -m pytest tests -v
```
The tests exercise the fail-closed path with no Trust or Governance running. They cover the low-trust, policy-deny and pass paths by monkeypatching `_check_trust` and `_check_policy`.

Run on its own:
```bash
cd services/marketplace && TRUST_URL=http://localhost:8002 GOVERNANCE_URL=http://localhost:8009 \
  uvicorn app.main:app --port 8016
curl -s localhost:8016/health
curl -s -X POST localhost:8016/marketplace/listings -H 'Content-Type: application/json' \
  -d '{"name":"Tutor Agent","asset_type":"agent","publisher":"agent-1","risk_level":"S1"}'
curl -s -X POST localhost:8016/marketplace/listings/<id>/publish
curl -s "localhost:8016/marketplace/listings?status=published"
```

## Changing it
- **Keep the gate fail-closed.** `test_publish_fails_closed_without_trust_or_governance` asserts that `"fail-closed"` appears in the reason. Don't copy the fail-open pattern from connector-bus's Brain check.
- **Publisher ids containing `/`.** The publisher string is put straight into the Trust URL path. Trust's route is `/trust/{entity_id}`, a plain path parameter that does not match `/`. So a URI-style publisher such as the default `aepx://agent/anonymous` should not resolve on a live Trust, and the gate then fails closed. By contrast, connector-bus strips a sender URI down to its last segment. Check this against a running Trust before relying on URI publishers.
- Governance's `/policy/evaluate` takes `risk_level` as a **query parameter**, and the seed ceiling is `S2`. The `S3` and `S4` levels are denied by default.
- The `risk_level` label on a listing is not validated. An unrecognised label is denied by Governance.
- No code in services/, connector-bus/, sdk/ or console/ calls `/marketplace/*` today. `platform/aepx-console` only registers `MARKETPLACE_URL`. Recheck with `grep -rn "MARKETPLACE_URL\|/marketplace/" services connector-bus sdk platform console`.
- There is no OpenAPI contract in `schemas/openapi/`.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-governance: the policy check
- aepx-governance-policy: risk ceilings
- aepx-svc-billing: marketplace fees are listed as a billing use case
