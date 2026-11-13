# Real PostgreSQL identity-role acceptance

This test starts an ephemeral PostgreSQL 16 instance in CI, applies the
existing authority, revision and least-privilege migrations, then queries
PostgreSQL's `has_table_privilege` and `has_schema_privilege` functions.

Checks include SELECT access for both roles; absence of reader
INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER; absence of publisher
TRUNCATE; absence of schema CREATE; and NOLOGIN for both roles.

**Safety:** The test refuses to run unless both
`HITL_ROLE_TEST_ISOLATED=yes` and `HITL_ROLE_TEST_DSN` are set, and it
checks the actual database is `identity_test` on a local host before
executing migrations. Do not port-forward a production DB to localhost.

This does not test login-role inheritance, tenant RLS, ownership bypass,
live JWT, or IdP sync. No OCI or production migration is executed.
