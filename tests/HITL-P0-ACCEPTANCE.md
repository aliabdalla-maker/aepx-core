# AEP-X P0 HITL acceptance runbook

## GitHub status reconciliation

PR #46 (outbox exhaustion recovery) and PR #52 (opt-in dispatcher) were **merged** when this gate was authored. Do not cherry-pick or merge them again. The next step is validating their combined behavior on the same release SHA.

## CI gate

The main CI workflow previously installed `httpx2` instead of `httpx`, and did not explicitly execute root HITL tests. The new `HITL P0 acceptance` workflow has two independent jobs:

- **offline:** run the repository-root HITL suite with the governance dependencies.
- **postgres:** start disposable PostgreSQL 16, apply staging, outbox lease and tenant-FK migrations, create a restricted non-owner/non-BYPASSRLS role and execute actual tenant, concurrency and outbox fault tests.

The Postgres job is self-contained; no OCI credentials, production secrets, remote databases or real tool adapters are required. If either job fails, retain the draft PR, inspect job logs and fix the underlying failure. A queued or missing workflow is **not** a pass.

## Acceptance evidence required

1. Both HITL jobs pass on the exact proposed release commit.
2. Verify RLS is enforced with the restricted role and missing tenant context exposes no rows.
3. Verify competing approvals and consumption produce exactly one winner and outbox event.
4. Verify multi-worker `SKIP LOCKED` claims, stale settlement fencing and expired-lease recovery.
5. Verify exhausted crashed leases become `dead` and cannot be claimed.
6. Demonstrate a crash after external delivery can replay the same event ID: downstream idempotency remains a mandatory separate gate.
7. Verify outbox grants, schema migration order, backup/rollback rehearsal and operator dead-letter procedures.
8. Obtain security and release review before any staging dispatcher enablement.

## Remaining limitations

The dispatcher remains disabled unless both the trusted caller and `HITL_DISPATCH_ENABLED=yes` explicitly enable it. No real adapter is supplied. These tests cannot establish exactly-once external effects; they establish durable DB fencing and the need for event-ID deduplication. Production is not changed by this PR.
