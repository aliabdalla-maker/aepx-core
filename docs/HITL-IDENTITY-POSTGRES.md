# Authoritative identity database — staged integration

This change adds a **read-only** PostgreSQL adapter to the existing
`enforce_identity_policy` contract and a migration for authoritative
membership and revocation records. A trusted IdP synchronizer, not the
HITL HTTP process, must provision and update the records.

## Required before live route enforcement
1. Complete review of shared JWT PR #73. Require a cryptographically
   verified, issuer-bound `jti` claim and propagate it to the principal.
2. Provision isolated staging PostgreSQL and apply the migration using a
   migration role; grant only SELECT to the dedicated identity-check role.
3. Implement an authenticated, monitored IdP membership and revocation
   synchronization service, with freshness limits and fail-closed behavior
   if the authority is stale or unavailable.
4. Wire `enforce_postgres_identity` into **all** HITL HTTP routes after
   JWT verification and before authorization or database mutation.
5. Run cross-tenant, revocation, outage, concurrency and end-to-end tests.

**Not production-ready:** an empty memberships table denies everyone;
a missing revocation row does NOT prove a token is valid if synchronization
is stale. The current adapter does not itself enforce synchronization
freshness or bind `jti` to a live route. Do not deploy it as a complete
revocation solution. No external execution is enabled.

## Freshness enforcement (added)

Both membership and revocation queries now require a per-tenant, per-issuer
`identity_authority_sync` heartbeat with `healthy=true` and
`synced_at` within the last 60 seconds, evaluated by PostgreSQL time.
A missing, stale or unhealthy heartbeat denies authorization. The trusted
synchronizer must update the heartbeat **only after** completing the full
membership and revocation refresh. Synchronizer implementation, race-safe
snapshot publication and live route wiring remain outstanding. The 60-second
threshold is an initial security default and requires operational validation.
