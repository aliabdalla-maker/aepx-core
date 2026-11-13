# Post-PR #56 validation gate (draft only)

This branch adds an opt-in, one-batch **local PostgreSQL** dispatcher.
It does not enable remote MCP transport, production execution or OCI deployment.

## Offline checks
```bash
python3 -m unittest discover -s tests -p 'test_aepx_hitl_dispatcher.py' -v
python3 -m unittest discover -s tests -p 'test_aepx_hitl_outbox.py' -v
python3 -m unittest discover -s tests -p 'test_aepx_hitl_execution_receipts.py' -v
```

## Disposable PostgreSQL integration checks
Use the repository's existing HITL PostgreSQL CI workflow with its disposable
PostgreSQL service, migrations in order, restricted non-owner test role, and
`HITL_TEST_DATABASE_URL` plus `HITL_TEST_DISPOSABLE=yes`.
Never point this test at production. Validate tenant isolation, concurrent
local receipt deduplication, lease expiry, stale settlement, and dead letters.

## Required before operational enablement
- Confirm CI results and fix any failing existing tests.
- Prove non-owner RLS on all dispatcher connections.
- Add end-to-end disposable-DB dispatcher tests with real connections.
- Implement heartbeat or enforce a bounded local callback runtime shorter
  than the lease. Otherwise a slow callback can finish after lease expiry.
- Review error redaction, audit trails, retry jitter and alerting.
- Do not use this module for remote MCP actions; those require separate
  provider idempotency and external-side-effect recovery.
- No merge, no deployment, no real external execution.
