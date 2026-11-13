# HITL outbox lease foundation

The PostgreSQL outbox lease module provides tenant-scoped claims using `FOR UPDATE SKIP LOCKED`, bounded batches, retry eligibility, lease ownership checks and dead-letter status after a configured attempt limit. A migration adds lease metadata.

This is **not a running dispatcher**. No transport, external MCP execution, credentials or OCI resources are configured. A delivery worker must send events, apply idempotency at the consumer, and call `settle` after verified delivery. A worker crash after delivery and before settlement can cause duplicates: **at-least-once delivery**, never exactly once. Lease expiry allows another worker to reclaim work; consumers must deduplicate by event ID.

Apply both HITL migrations in order only in an isolated reviewed staging database. Verify PostgreSQL RLS with a non-owner application role and two tenants. Add live concurrent-worker tests, forced failures, retry/dead-letter recovery, lease fencing and audit monitoring. Do not enable consequential tools before authenticated HITL APIs and end-to-end acceptance.
