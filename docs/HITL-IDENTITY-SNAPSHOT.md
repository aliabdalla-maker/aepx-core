# Trusted IdP snapshot publisher

`publish_identity_snapshot` writes active memberships, revoked JWT IDs
and a healthy synchronization heartbeat in one PostgreSQL transaction.
It locks the tenant/issuer heartbeat row to serialize writers. SQL errors
roll back the entire transaction. A snapshot captured more than 30 seconds
ago or over five seconds in the future is denied.

## Integration requirements

- Caller MUST authenticate the IdP authority, verify the snapshot is
  complete and authentic, and validate tenant/issuer mapping before invoking.
- `revoked_tokens` MUST be a complete current revocation set; passing a
  delta would delete older revocations and is unsafe.
- Provision a dedicated writer with least-privilege table access. The
  HITL HTTP runtime must have read-only access and must not invoke this.
- Configure a separate synchronizer that refreshes each active tenant/issuer
  at least every 60 seconds. Detect missed heartbeats and alert.
- The publisher does NOT protect against an older but still fresh snapshot
  overwriting a newer snapshot. Add monotonic authority revision numbers
  before multiple synchronizers or distributed IdP feeds are enabled.
- Review PostgreSQL transaction isolation and test against an ephemeral DB.
  This code is not a live IdP connector and is not deployed.
- Complete verified JWT `jti` propagation and enforce the existing
  `enforce_postgres_identity` policy on every HITL route before rollout.

No external effect, production deployment or migration is enabled.
