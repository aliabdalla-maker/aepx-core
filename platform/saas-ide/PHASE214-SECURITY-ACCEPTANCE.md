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

## Phase 2.15 incremental hardening (unverified until CI completes)
- Added `execution_status` tenant-scoped, read-only operational lookup.
- Added evidence-backed `resolve_unknown` transition with durable evidence reference, operator identity, and audit event; never resets to reserved.
- Added PostgreSQL tests for evidence requirements, cross-tenant status isolation, no replay, and stale-dispatch crash simulation.
- **Not yet implemented:** authenticated operator role enforcement for reconciliation; independent provider evidence validation; provider-specific idempotency propagation; permission-revocation race coverage. The internal reconciliation function must not be exposed to untrusted callers.
- These tests simulate an interrupted worker through a stale timestamp; they are not a full process-kill/remote-side-effect integration test.

## Phase 2.16 implementation — release still HOLD
- Reconciliation now requires an authenticated tenant owner/admin principal matching the recorded actor, plus an independent trusted evidence-verifier callback. There is no public reconciliation API; provider verification integrations are not yet configured.
- Dispatch now revalidates requester (owner/admin/editor) and approver (owner/admin) membership in PostgreSQL immediately before claiming execution. A PostgreSQL integration test downgrades the member after approval and asserts dispatch denial.
- MCP transport supports an optional `IDE_MCP_<SERVER>_IDEMPOTENCY_CONTRACT=http-header-v1` header contract using the stable execution key. It is off by default. This is **not proof of provider-side exactly-once semantics**; enabling requires documented provider acceptance and end-to-end verification.
- Previous stale-dispatch test simulates a crash; a true killed-process and remote-side-effect test remains outstanding.
- CI is required on the final commit; passing checks on older commits do not authorize release.
- Explicit production release authorization and independent security sign-off have **not** been granted.
