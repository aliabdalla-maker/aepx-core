# Post-PR #56 HITL dispatcher validation (draft only)

This branch hardens the existing **opt-in, transport-adapter** dispatcher.
It does not enable remote MCP transport, OCI deployment, or production execution.
Default mode remains dry-run. Operational delivery requires both
`enabled=True` and `HITL_DISPATCH_ENABLED=yes`, and an independently reviewed
idempotent adapter. Remote delivery and DB settlement are not atomic.

## Offline CI
```bash
python3 -m unittest discover -s tests -p 'test_aepx_hitl_dispatcher.py' -v
python3 -m unittest discover -s tests -p 'test_aepx_hitl_outbox.py' -v
```

## Disposable PostgreSQL integration gate — NOT YET VERIFIED
Run the repository's existing PostgreSQL HITL test suite against a **disposable**
database with the complete migrations applied in order, a restricted non-owner
test role, and `HITL_TEST_DATABASE_URL` plus
`HITL_TEST_DISPOSABLE=yes`. Never point tests at production.

Prove two-tenant RLS isolation, concurrent receipt deduplication, lease expiry,
stale settlement rejection, exhaustion recovery and dead-letter behavior.

## Before enabling a real adapter
- Verify CI and disposable PostgreSQL test results.
- Enforce non-owner RLS and authenticated tenant identity on all connections.
- Add real-DB dispatcher integration tests and crash injection.
- Ensure bounded delivery runtime or lease renewal before lease expiry.
- Ensure remote consumers deduplicate by stable event ID; no exactly-once claim.
- Add retry jitter, monitoring, rate limits and redacted audit records.
- Do not merge, deploy or enable external execution without explicit approval.
