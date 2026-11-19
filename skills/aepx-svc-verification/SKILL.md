---
name: aepx-svc-verification
description: Verification Engine (Anti-Hallucination V2) for AEP-X. It scores claims into a truth score and a GREEN/AMBER/RED/GREY confidence band. Use when working on, debugging, calling or extending the verification service in aepx-core, including when oracle-bridge decisions come back with an unexpected band.
---

# Verification Engine service (`services/verification`)

## Role
This service owns evidence correlation, truth and confidence scores, and citations (docs/Microservices-Architecture-v2.md §3). The docs keep it separate from the Safety Engine: Safety does risk classification and escalation, and Verification does evidence scoring. Its band labels (GREEN/AMBER/RED/GREY) deliberately differ from Safety's labels. The code says "Do not merge these label sets".

The oracle bridge uses its score as the on-chain `confidence` and `band` (RFC-0008 §4.2). That keeps Law 3 (Evidence Before Assertion) intact for on-chain consumers (RFC-0008 §6).

The current implementation is a **scaffold**. The truth score depends only on the number of `source_ids`, and the Kafka publish is only a `print`.

## Where
- Code: `services/verification/app/main.py`.
- Compose service `verification`, host port **8011** -> container 8000, `depends_on: [knowledge, kafka]`.
- There is no environment block in docker-compose.yml.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"verification"}` |
| POST | `/verify` | Score a set of claims | Request is `VerifyIn`: `{workflow_id: str, claims: [{text: str, source_ids: [str] = []}]}`. Response is `{workflow_id, results: [{claim, truth_score, confidence_band, citations}], summary: {workflow_id, claim_count, truth_score, confidence_band, citations}}` |

Scoring and banding:
- **Per claim:** `truth_score = min(100, 35 * len(source_ids))`.
- **Summary:** `truth_score` is the mean of the per-claim scores (0.0 when there are no claims). Its band is computed from that mean.
- **Bands:** `CONFIDENCE_BANDS = [(95,"GREEN"), (80,"AMBER"), (60,"RED"), (0,"GREY")]`. A score gets the first band whose threshold it meets or exceeds.
- **Consequence:** a single claim scores 0, 35, 70 or 100. That gives GREY, GREY, RED or GREEN. A single claim never gets AMBER, and one claim with one source is always GREY.

## Configuration
The code reads no environment variables.

## Data & dependencies
- **Storage:** none. The service is stateless. `verification.results` exists in `schemas/sql/002_v2_additions.sql`, but the code does not use it yet. Its columns are `workflow_id UUID`, `claim_count`, `truth_score`, `confidence_band CHECK IN (GREEN, AMBER, RED, GREY)`, `citations JSONB` and `created_at`.
- **Kafka (intended):** it should publish `verification.completed` with the `summary` payload. That matches the documented `{workflow_id, claim_count, truth_score, confidence_band, citations[]}`. Today `_publish()` only prints `[verification] would publish to ...`. Governance subscribes to `verification.completed`, so these events are **not** in the audit trail yet.
- **Kafka consumer:** `consume_workflow_events()`, meant to consume `workflow.completed`, is an empty placeholder. The thread starts and exits immediately.
- **Other services:** it calls none. Compose lists `knowledge` in `depends_on`, but the code does not call Knowledge.
- **Callers:**
  - `services/oracle-bridge` `_verify()` POSTs `/verify` with `workflow_id = "oracle-<request_id|adhoc>"` and one claim whose `source_ids` is `[ai_source]`. It reads `summary.truth_score` and `summary.confidence_band`. If Verification is unreachable, the bridge degrades to confidence 0 and band GREY.
  - Gateway, Brain and the aepx-console poll `/health`.

## Run & test
```bash
pip install -r services/verification/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/verification
cd services/verification && python -m pytest tests -v
```

Run on its own:
```bash
cd services/verification && uvicorn app.main:app --port 8011
curl -s localhost:8011/health
curl -s -X POST localhost:8011/verify -H 'Content-Type: application/json' \
  -d '{"workflow_id":"wf-1","claims":[{"text":"F = ma","source_ids":["s1","s2","s3"]},{"text":"unsupported"}]}'
```

## Changing it
- **The response shape is a contract.** oracle-bridge reads `summary.truth_score` (0–100, which it rounds and clamps to uint8 for `fulfillDecision`) and `summary.confidence_band`. The on-chain `AEPXOracle` stores `band` as a string. Renaming either field silently turns every oracle decision GREY.
- If you change `truth_score()` or the band thresholds, update:
  - `tests/test_health.py::test_verify_bands`, which expects 3 sources to be GREEN and 0 sources to be GREY
  - any oracle-bridge expectations
- If you wire a real Kafka producer, follow the kafka-python pattern used elsewhere (`KAFKA_BOOTSTRAP`, default `kafka:9092`, as in brain and oracle-bridge). Keep the topic name `verification.completed` exactly, because Governance matches topic names exactly.
- If you add Postgres persistence, note that `verification.results.workflow_id` is a `UUID`. oracle-bridge sends non-UUID ids such as `oracle-adhoc`.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "VERIFICATION_URL\|/verify\"" services connector-bus sdk platform console`.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-oracle-bridge: its main caller
- aepx-svc-knowledge: the intended evidence source
- aepx-svc-governance: audits `verification.completed`
- aepx-blockchain: for how the band lands on-chain
