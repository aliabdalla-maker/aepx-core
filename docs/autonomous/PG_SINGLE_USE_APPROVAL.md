# Staging-only PostgreSQL single-use approval nonces

`platform/saas-ide/backend/sql/aepx_iteration_approval_nonce.sql` adds a tenant-RLS approval nonce table and `aepx_iteration.consume_approval(...)`. A successful call row-locks the reviewed work item and approval in a fixed order, verifies the live lease fence, reviewer reference, expiry and unconsumed nonce, then marks the nonce consumed. A second call fails. The script does not apply itself, provision a nonce, grant access or complete an iteration.

**Not a production authorization boundary:** PostgreSQL `app.tenant_id` is a user-settable GUC; a reviewer ID string is not authentication. An attacker with direct INSERT/UPDATE on `approval_nonce` can forge approvals. A trusted controller must authenticate tenant and reviewer, validate signature and artifact bytes, create the nonce in an isolated privilege domain and restrict worker roles to approved operations. Also require a trusted atomic completion transaction; otherwise consuming a nonce and completing an iteration are not atomic. PostgreSQL acceptance and concurrency tests, privilege grants and key rotation are still pending. Terminal completion remains blocked.

## Opt-in disposable PostgreSQL replay acceptance

After applying reviewed iteration and approval migrations to a dedicated local disposable database and configuring a non-superuser/non-BYPASSRLS fixture role, run:

```bash
bash scripts/test_aepx_pg_approval_nonce_acceptance.sh --execute aepx_test_approval
```

The fixture tests one successful consumption, replay denial, expired nonce, stale fence, reviewer mismatch, expired work lease, and cross-tenant isolation. It requires FORCE RLS on both tables, rolls back all fixture changes and does not apply migrations. The GitHub Actions job only runs static safety-contract checks. **No live PostgreSQL test has been run.** Separate two-session concurrency tests, trusted tenant binding, privilege restrictions and atomic completion are required before production use.

## Two-session replay race (opt-in, not CI-executed)

After applying both migrations to a disposable local `aepx_test_` database, use a non-superuser/non-BYPASSRLS fixture role with test-only INSERT/DELETE permissions:

```bash
python scripts/test_aepx_pg_approval_concurrency.py --execute aepx_test_approval
```

The harness creates a transactionally committed, random nonce/iteration fixture, starts two independent `psql` connections, holds the first consumption transaction open, verifies the second blocks until the first commits, then checks that the second fails as a replay and only one nonce is consumed. Cleanup is attempted in `finally`. The test has not been run against PostgreSQL; CI only checks the offline harness contract. Run only in a dedicated disposable database: the harness creates and deletes rows and does not provision or migrate databases. This does not fix direct-DML privileges, untrusted tenant GUCs, authenticated approvals or atomic completion.
