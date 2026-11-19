# Isolated PostgreSQL snapshot concurrency acceptance

This draft PR adds an integration test using an ephemeral PostgreSQL 16
service. Two concurrent publishers race with the same revision for the same
tenant/issuer. Acceptance: exactly one succeeds, the losing transaction is
rolled back, the membership and revocation records agree, revision 1 cannot
be replayed, and revision 2 can replace the snapshot.

The test requires both `HITL_IDENTITY_TEST_DSN` and
`HITL_IDENTITY_TEST_ISOLATED=yes`. It creates schema/table objects and
writes records. NEVER use a production or shared staging database.

This is test infrastructure, not proof of production readiness. The workflow
must finish successfully before its assertions can be considered verified.
The complete IdP connector, verified JWT jti, live HITL route enforcement,
role isolation, real migration rehearsal and 1,000-pass acceptance remain
outstanding.
