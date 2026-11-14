# Transactional PostgreSQL budget foundation

This is an **unapplied migration** for disposable staging. It does not call LLMs, authorize spending or replace the offline JSON ledger.

- `tenant_budget` holds tenant-scoped token and USD caps and committed usage.
- `reservation` stores tenant-scoped stable request IDs and reserved/settled amounts.
- `reserve` locks the tenant budget row before checking capacity and inserting; a replay with identical values returns `already_reserved`.
- `settle` locks the budget and reservation rows, enforces actual usage within reservation, and releases only the unused amount. Unknown in-flight reservations remain charged until operator-reviewed reconciliation.
- Both tables force row-level security; functions use invoker rights and revoke default PUBLIC execution.

## Required before integration

1. Review migration against the existing schema and migration framework; run PostgreSQL integration tests including two-worker contention, replay, rollback, tenant isolation, RLS bypass, crash and numeric overflow.
2. Provision tenant rows through a privileged audited control plane. Set `app.tenant_id` only from a verified OIDC tenant identity inside the same transaction (`SET LOCAL`), and ensure untrusted SQL cannot change this session setting. **A custom GUC alone is not an authentication boundary.** Prefer a role-bound identity mapping or a trusted server-side security boundary.
3. Use a dedicated non-owner application role with no BYPASSRLS or DDL rights. Grant only the required schema/table/function permissions after review.
4. Extend reservations to wall-clock and repair-attempt caps; add trusted provider billing reconciliation, immutable audit events and per-request idempotency at the external provider.
5. Wire the transaction service to a fenced worker only after sandbox and CI acceptance. Never release unknown in-flight reservations automatically.

Static tests validate SQL text only; no PostgreSQL migration or concurrency test has run.
