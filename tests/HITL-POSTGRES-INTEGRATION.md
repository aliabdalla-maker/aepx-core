# HITL PostgreSQL integration gate

**Never use production or a shared database.** Provision a disposable PostgreSQL database and apply migrations in this order:

1. `db/migrations/20261113_hitl_staging.sql`
2. `db/migrations/20261113_hitl_tenant_fk.sql`

Create a separate login role for integration tests. The role must be **NOSUPERUSER NOBYPASSRLS**, must not own the HITL tables, and must have only `USAGE` on schema `hitl`, `SELECT/INSERT/UPDATE` on its tables, and `USAGE/SELECT` on the `hitl.events` identity sequence. Do not grant `TRUNCATE`, `DELETE`, `CREATE`, `BYPASSRLS`, or ownership. Use a trusted, private test database DSN.

Run:

```bash
export HITL_TEST_DISPOSABLE=yes
export HITL_TEST_DATABASE_URL='postgresql://<restricted-role>:<password>@<private-host>/<disposable-db>'
PYTHONPATH=services/governance python -m unittest discover -s tests -p 'test_hitl_postgres_integration.py' -v
```

The suite skips unless both explicit environment settings are present. It asserts that the connected role is neither superuser nor BYPASSRLS nor the approvals table owner. It tests request, cross-tenant denial, self-approval denial, decision, consumption, replay and second-consumption denial. **This is a functional acceptance test, not a substitute for concurrency/load testing.** It writes durable records; destroy the disposable database after the run.

Still required: simultaneous consumption and competing decisions, outbox worker recovery, grants verification for all tables, migration rollback rehearsal, and independent security review. No OCI deployment is performed by this test.
