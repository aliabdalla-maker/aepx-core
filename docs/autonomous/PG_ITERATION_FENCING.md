# PostgreSQL fenced iteration state (foundation)

The staging-only migration `platform/saas-ide/backend/sql/aepx_iteration_fenced.sql` defines tenant-scoped work items, one incomplete iteration per tenant, a lease claim with monotonic fencing token, and a row-locked six-stage transition function. An expired lease may be replaced with a higher fence; a stale owner/fence or expired lease cannot advance the record. Completion clears the lease.

**Not ready for production.** The SQL is not applied or executed in CI. The custom `app.tenant_id` setting is **not authenticated** by PostgreSQL and must be bound to a trusted session authority. This schema does not verify signatures, evidence bytes, test results or reviewer approvals; the `completed` stage currently accepts a string reference and must be gated by trusted approval and evidence checks before any real workflow. It does not implement provider dispatch, billing, a lease heartbeat, crash-injection tests or external worker fencing.

Next: add disposable PostgreSQL acceptance tests with a non-owner non-BYPASSRLS role; exercise two concurrent connections and lease expiry; build trusted approval+evidence completion gates; authenticate tenant identity; add durable provider dispatch claims and billing reconciliation. Do not apply to production or enable autonomous execution.

## Fenced lease renewal

`aepx_iteration.renew(tenant,number,owner,fence,seconds)` serializes on the work-item row, checks the current unexpired lease and exact owner/fence, rejects completed iterations and bounds renewal to 1–600 seconds from the current database clock. Renewal does not increment the fence. Once expired, the worker must obtain a new claim/fence; it cannot revive an old lease.

**Verification still required:** Exercise renewal, competing claim, expiry, transaction rollback and concurrent workers against a disposable PostgreSQL database with a non-BYPASSRLS role. Tenant GUC remains untrusted without server-side authentication. Renewal is not evidence approval, provider dispatch authorization or distributed worker isolation.

## Opt-in disposable PostgreSQL acceptance

A rollback-only acceptance fixture is provided in `tests/sql/aepx_iteration_pg_acceptance.sql` and the guarded launcher `scripts/test_aepx_pg_iteration_acceptance.sh`. After a reviewed migration is applied to a **dedicated local disposable** database named `aepx_test_...`, and a non-superuser/non-BYPASSRLS role with appropriate fixture permissions is configured, run:

```bash
bash scripts/test_aepx_pg_iteration_acceptance.sh --execute aepx_test_iteration
```

The fixture tests first claim, live-lease takeover rejection, renewal, wrong owner, stage ordering, forced expiry, stale fence rejection, reclaimed lease and tenant isolation, then rolls back its fixture data. The launcher never applies migrations. The CI job checks only static fixture safety and does not execute PostgreSQL. **Not covered yet:** true two-connection races, SIGKILL recovery, trusted tenant identity, approval/evidence verification, or provider billing.

## Terminal completion is intentionally disabled

`aepx_iteration.advance(..., 'completed', ...)` now raises `iteration completion requires trusted evidence and approval gate` even for a valid current worker lease. The reviewed stage remains reachable. This blocks the unsafe previous behavior where arbitrary evidence text could mark an iteration completed.

Before introducing a trusted completion function, require authenticated reviewer identity, digest-verified immutable evidence for every stage, passing test evidence, current fencing token, one-time approval consumption and an atomic PostgreSQL transition. Test tampering, replay, concurrent workers, stale leases and crash recovery against a disposable database. Until then **no PostgreSQL iteration can be marked completed through this function**; this is an intentional safety constraint, not a completed orchestration feature.

## Canonical stage evidence digests

All non-terminal stage transitions now require exactly `sha256:` followed by 64 lowercase hexadecimal characters. Malformed references are rejected before any state update. The rollback-only acceptance fixture checks a malformed digest and uses syntactically valid digests for positive stage transitions.

**Security boundary:** A SHA-256-shaped string is not proof of artifact existence, immutable storage, correct content, successful tests or reviewer authorization. A trusted service must open and hash the actual artifact, bind it to the tenant/iteration/stage/fence, record provenance and consume approval atomically. Terminal completion remains blocked. The acceptance SQL and static tests have not been executed against a database in this PR.
