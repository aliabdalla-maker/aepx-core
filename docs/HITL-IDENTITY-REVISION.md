# Monotonic IdP snapshot revisions

This change requires `revision` (positive PostgreSQL bigint) for every
identity snapshot. The publisher serializes tenant/issuer updates using
`SELECT ... FOR UPDATE`, rejects a revision less than or equal to the
stored revision, and commits snapshot rows and revision together.

## Rollout

1. Apply `20261113_hitl_identity_revision.sql` in isolated staging.
   It sets existing heartbeats unhealthy; service access will fail closed
   until a trusted complete snapshot is published.
2. Configure the trusted IdP feed to emit a strictly increasing, durable,
   per-tenant/issuer revision, not a wall-clock timestamp.
3. Ensure the snapshot is authenticated and complete, including ALL current
   revocations. A revision only orders data; it does not authenticate it.
4. Test concurrent publishers, database rollback, restart, missing
   heartbeat, stale data and cross-tenant access against real PostgreSQL.
5. Verify the 60-second freshness gate and JWT jti integration before
   enabling live HITL routes.

This is not an IdP connector or a production deployment. No external
execution is enabled.
