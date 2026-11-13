# HITL PostgreSQL integration gate

**Never run against production or a shared database.** The repository's `.github/workflows/hitl-acceptance.yml` provisions a disposable PostgreSQL 16 service and a restricted non-owner application role. The acceptance workflow runs on pull requests, merge queues, pushes and manual dispatch.

Migrations are applied in the workflow in this order:

1. `db/migrations/20261113_hitl_staging.sql`
2. `db/migrations/20261113_hitl_outbox_lease.sql`
3. `db/migrations/20261113_hitl_tenant_fk.sql`
4. `db/migrations/20261113_hitl_recovery_audit.sql`
5. `db/migrations/20261113_hitl_execution_receipts.sql`
6. `db/migrations/20261113_hitl_remote_delivery_receipts.sql`

The application role must be **NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE**, must not own the HITL tables, and receives schema USAGE, table SELECT/INSERT/UPDATE and sequence USAGE/SELECT. Never grant TRUNCATE, DELETE, CREATE, BYPASSRLS or ownership. CI checks the role and database identity before executing tests.

For a separately provisioned **disposable** database with the same migrations and restricted grants:

```bash
export HITL_TEST_DISPOSABLE=yes
export HITL_TEST_EXPECTED_DATABASE='<disposable-db>'
export HITL_TEST_DATABASE_URL='postgresql://<restricted-role>:<password>@<private-host>/<disposable-db>'
PYTHONPATH=services/governance python -m pytest tests/test_hitl_postgres_integration.py -v
```

The test class skips unless the database URL and disposable opt-in are set. When enabled, it fails closed unless the expected database name matches and the role is restricted, non-owner, and cannot create databases or roles. The CI workflow sets both and provisions its own disposable database. Tests include cross-tenant isolation, concurrent approval and consumption, local execution receipts, remote reconciliation, outbox recovery and health. A successful run is necessary but **not sufficient** for production qualification.

Remaining acceptance work: enforced callback isolation/timeout, process-crash fault injection, external MCP idempotency verification, alert delivery, migration rollback rehearsal, and independent security review. No OCI deployment is performed by this workflow.
