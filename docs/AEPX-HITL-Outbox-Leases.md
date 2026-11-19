# HITL outbox lease foundation

The PostgreSQL outbox lease module provides tenant-scoped claims using `FOR UPDATE SKIP LOCKED`, bounded batches, retry eligibility, lease ownership checks and dead-letter status after a configured attempt limit. A migration adds lease metadata.

This is **not a running dispatcher**. No transport, external MCP execution, credentials or OCI resources are configured. A delivery worker must send events, apply idempotency at the consumer, and call `settle` after verified delivery. A worker crash after delivery and before settlement can cause duplicates: **at-least-once delivery**, never exactly once. Lease expiry allows another worker to reclaim work; consumers must deduplicate by event ID.

Apply both HITL migrations in order only in an isolated reviewed staging database. Verify PostgreSQL RLS with a non-owner application role and two tenants. Add live concurrent-worker tests, forced failures, retry/dead-letter recovery, lease fencing and audit monitoring. Do not enable consequential tools before authenticated HITL APIs and end-to-end acceptance.

## Fenced settlement contract
A successful claim returns the incremented attempt counter in its fourth field. Pass that counter as `attempt_number` to `settle`. Settlement now requires matching tenant, event ID, worker ID, unexpired lease and exact attempt number. This prevents a stale worker with the same worker ID from settling a newer lease attempt. It does not remove the need for idempotent external consumers or live PostgreSQL concurrency tests.

## Crash exhaustion recovery
`reap_exhausted(connection, tenant_id=..., max_attempts=8)` atomically dead-letters exhausted pending rows and expired leases using `SKIP LOCKED`. A worker supervisor must invoke it periodically for each **verified** tenant. It does not send messages, restore failed business operations, or automatically requeue dead letters. Operator-led replay must be reviewed for idempotency and authorisation. PostgreSQL integration tests and authenticated worker scheduling remain outstanding.
