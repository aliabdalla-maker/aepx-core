# Atomic identity decision — PostgreSQL acceptance

The isolated PostgreSQL 16 acceptance exercises the production
`enforce_postgres_identity` path against real tables and verifies:
fresh active membership allows, a different tenant denies, an exact
revoked token denies, stale authority denies, and unhealthy authority
denies. Each decision uses the atomic single-statement query.

The test requires `HITL_IDENTITY_TEST_ISOLATED=yes`, a local
PostgreSQL connection and database named exactly `identity_test`.
The CI job provisions a disposable PostgreSQL service; it does not
use OCI or production credentials.

Remaining acceptance: concurrent snapshot replacement versus identity
decisions, restricted read-only roles with RLS, real HTTP HITL endpoints,
JWT/JWKS integration, and the 1,000-pass release suite. CI conclusions
must be inspected before considering this verified.
