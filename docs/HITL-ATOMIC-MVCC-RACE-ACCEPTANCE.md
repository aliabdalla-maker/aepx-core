# Atomic HITL identity MVCC race acceptance

This test suite checks the real PostgreSQL identity decision while a
separate writer transaction has inserted an uncommitted token revocation
or deactivated a membership. It confirms the reader sees the last
committed state and that a subsequent decision denies after commit.

It uses a disposable PostgreSQL 16 service and requires both an explicit
isolated opt-in and a local database named exactly identity_test.

**Important:** MVCC consistency does not guarantee that a revocation
which commits immediately after a successful decision will retroactively
deny that decision. For high-risk external effects, revalidate at
dispatch/commit, preserve HITL authorization expiry and use a fenced
transactional execution boundary.

Remaining: multi-worker adversarial concurrency, RLS role tests, actual
HTTP endpoint acceptance, JWKS/IdP transport and release gate.
No production database, deployment or external execution was used.
