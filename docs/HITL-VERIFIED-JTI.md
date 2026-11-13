# Verified JWT jti identity boundary

`enforce_verified_claims_identity` requires a `jti`, subject, issuer and
tenant from **already cryptographically verified** JWT claims. It checks
the expected tenant and calls the PostgreSQL-backed membership, revocation
and authority-freshness policy. Missing/malformed claims and unavailable
database checks deny access.

**Important:** This is an internal boundary, NOT an authentication
endpoint. A plain dict does not prove that claims were verified. Never
pass user-controlled request JSON to this function.

## Remaining P0 work
1. Resolve shared JWT verifier PR #73 and require `jti` in its
   cryptographic decode contract; keep RS256, issuer and audience checks.
2. Wire only the verified decoder output into this boundary; avoid
   re-decoding a token with different validation settings.
3. Integrate into all HITL HTTP endpoints BEFORE approval mutations.
4. Provide a trusted, authenticated, complete IdP sync feed with
   monotonic revision and restricted database roles.
5. Run end-to-end revocation, tenant mismatch, outage and concurrency
   tests against isolated PostgreSQL; verify CI success.

No live route, production migration, merge, deployment or external
execution is enabled by this PR.
