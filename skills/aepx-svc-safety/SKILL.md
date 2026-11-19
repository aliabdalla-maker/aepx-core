---
name: aepx-svc-safety
description: AEP-X Safety Engine. It validates answers against their evidence, returning the {answer, confidence, evidence, verification_status} contract, and flags unevidenced answers and empty workflows to Kafka safety.flagged. Use when working on, debugging, calling or extending the safety service in aepx-core.
---

# Safety Engine (`services/safety`)

## Role
Safety returns the evidence contract `{answer, confidence, evidence[], verification_status}` that Law 3, Evidence Before Assertion, requires. `docs/SOA-Architecture.md` and `docs/Microservices-Architecture-v2.md` both call this the contract the Safety Engine enforces (Instructional Manual §4.4). Confidence is an Alpha-stage placeholder based on evidence count. The docs say Verification Engine is meant to feed it a real truth score. Safety also listens to `workflow.completed` and flags suspicious workflows.

## Where
- Code: `services/safety/app/main.py`.
- Compose service: `safety`. Host port `8008` maps to container port `8000`.
- `depends_on: [trust, kafka]`. Compose sets no env vars, and the code never calls Trust.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{"status":"ok","service":"safety"}` |
| POST | `/safety/validate` | Validate an answer | Body `ValidateIn {answer: str, evidence: list[str] = []}`. Returns `{answer, confidence: len(evidence)*0.35, evidence, verification_status}`. |

Banding (`band_for`): `score = min(100, len(evidence)*35)`, compared against `CONFIDENCE_BANDS` of 95 Verified, 80 High, 60 Medium, and otherwise Unverified. In practice:

| Evidence items | Status |
|---|---|
| 0 or 1 | Unverified |
| 2 | Medium |
| 3 or more | Verified |

`High` is unreachable with the current step of 35, and `confidence` is not clamped (4 items give 1.4). There is no OpenAPI contract under `schemas/openapi/`.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Broker for both the producer and the consumer |

## Data & dependencies
- There is no storage and it makes no HTTP calls to other services.
- Kafka publishes `safety.flagged`:
  - `{"reason":"no_evidence","answer": answer[:200]}` when `/safety/validate` returns Unverified.
  - `{"reason":"empty_workflow", **event}` when a consumed `workflow.completed` has `step_count == 0`.
- Kafka consumes `workflow.completed` in a daemon thread started at import. The thread has a reconnect loop that sleeps 5s after any error ("load-bearing", see `services/governance`).
- Degrade behaviour is fail-open. The producer is lazy and retried like Workflow's. If there is no broker, flags are silently dropped and `/safety/validate` still answers. If `kafka-python` is not importable, the consumer thread exits immediately.
- `safety.flagged` is consumed by `services/governance` (it is in `_CONSUMED_TOPICS`, for audit). The ml-integration consumer is a placeholder.
- Callers over HTTP: `platform/aepx-console` and `services/gateway` (`/health`) via `SAFETY_URL`.

## Run & test
```bash
pip install -r services/safety/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/safety
cd services/safety && python -m pytest tests -v
```
Tests: health, Unverified with no evidence, and Verified with 3 items. The consumer thread spins harmlessly without a broker.

Run it alone:
```bash
cd services/safety && KAFKA_BOOTSTRAP=localhost:9092 uvicorn app.main:app --port 8008
curl -s -X POST http://localhost:8008/safety/validate -H 'content-type: application/json' \
  -d '{"answer":"F=ma","evidence":["s1","s2","s3"]}'
```

## Changing it
- The response keys `answer`, `confidence`, `evidence` and `verification_status` are the platform-wide evidence contract. The docs say Verification and connector responses reuse it, so do not rename them.
- If you change `CONFIDENCE_BANDS` or the 35-per-item step, fix the unreachable `High` band deliberately and update both tests.
- The `safety.flagged` payloads are audited by Governance. Keep `reason` present, and grep with `grep -rn "safety.flagged" services console`.
- Keep the consumer's `while True` reconnect loop and the lazy producer. Both exist to survive Kafka losing the compose startup race.
- The `empty_workflow` rule depends on Workflow's `step_count` field.

## Related skills
- aepx-svc-workflow (the producer of `workflow.completed`)
- aepx-svc-trust (a compose dependency only)
- aepx-svc-gateway
- aepx-svc-governance (audits `safety.flagged`), aepx-svc-verification (the deeper pipeline behind the same contract)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
