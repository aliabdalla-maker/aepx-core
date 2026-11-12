# Phase 2.14 — MCP dispatch ledger and recovery acceptance (draft)

Status: **HOLD — not approved for production**. PR #25 remains draft.

## Implemented controls
- Migration `007_phase214.sql`: tenant-scoped execution ledger with forced RLS and unique (tenant, approval) and (tenant, idempotency key) constraints.
- `consume_tool` reserves an execution in the same transaction as the approval transition and audit event.
- `begin_dispatch` uses a conditional state transition from `reserved` to `dispatching`; repeated dispatch is rejected.
- `mark_unknown` quarantines uncertain outcomes. `reconcile_stale` quarantines stale dispatching entries without retrying.
- The runtime marks exceptions, cancellation, and timeouts as unknown outcomes; it does not automatically replay them.
- PostgreSQL integration test covers ledger reservation, duplicate-dispatch denial, unknown outcome, and cross-tenant visibility.

## Explicit limits / residual risks
- A stable idempotency key is stored, but **provider-side idempotency is not implemented or asserted**. MCP servers may not support it.
- A crash after the database marks `dispatching` but before network I/O can leave an unknown outcome; conservative quarantine is intentional.
- A crash after remote side effects but before the response can leave an unknown outcome. Reconciliation requires independent provider evidence or human review.
- Run cancellation after `begin_dispatch` cannot undo a remote action already in flight. The current lock protects reservation/consumption, not remote execution completion.
- Ledger state `failed` is reserved for definitive failure; ambiguous failures are `outcome_unknown`.
- This is **at-most-once dispatch from the platform**, not exactly-once remote execution.
- Production external execution remains disabled.

## Release gates
- [ ] Dedicated Hybrid IDE CI green for the latest commit.
- [ ] Full repository CI green for the latest commit.
- [ ] Review concurrency, database grants, RLS and migration upgrade/rollback plan.
- [ ] Add crash-injection and permission-revocation integration tests.
- [ ] Document provider-specific idempotency contracts before enabling any side-effecting tool.
- [ ] Independent security review and explicit release authorization.
