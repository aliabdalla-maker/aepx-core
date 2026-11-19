# PostgreSQL identity integration safety

The identity concurrency integration test creates tables and writes rows.
Before running any DDL, it now checks the actual connected database name
(`identity_test`) and host (`127.0.0.1`, `localhost`, or `::1`).

Both environment opt-in variables are still required:
`HITL_IDENTITY_TEST_ISOLATED=yes` and `HITL_IDENTITY_TEST_DSN`.
The CI workflow provisions a local ephemeral PostgreSQL 16 service.

These guards reduce accidental production targeting but do not make an
untrusted local proxy or a forwarded connection safe. Never tunnel a
production database to localhost for this test. The integration test is
not proof of live IdP synchronization, JWT jti verification, or route
authorization. No migration or deployment is performed by this PR.
