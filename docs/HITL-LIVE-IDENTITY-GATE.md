# Live HITL authoritative identity gate (draft)

All three HITL mutation endpoints (consume, create request, decide request)
now require a cryptographically verified JWT and fresh PostgreSQL
membership/revocation authority. The gate is fail-closed: absent
`HITL_IDENTITY_READ_DATABASE_URL` yields 503; rejected identity yields 403.

The identity database URL MUST use a restricted read-only role. The existing
`HITL_DATABASE_URL` remains the separate approval-write database. The
IdP synchronizer must publish complete monotonic snapshots before any
endpoint can succeed. No fallback to development or in-memory identity.

Security review blockers before merge: avoid duplicate JWT verification
by consolidating shared decoder PR #73; pin JWKS egress and redirects;
add full HTTP + real PostgreSQL integration tests for all three endpoints,
including token revocation between approval and consumption; review
failure mapping and role separation; verify queued CI. Do not deploy
this change to production until IdP sync and read role exist. No external
execution is enabled.
