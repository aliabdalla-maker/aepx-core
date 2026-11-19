# HITL authoritative membership and revocation gate

`enforce_identity_policy` is a fail-closed **policy contract**, not a
membership database or revocation service. Both independent callbacks must
return the literal boolean `True` after querying trusted authoritative data.

Integration steps:
1. Verify the signed OIDC JWT using the shared verifier.
2. Extract authenticated subject, issuer, tenant and **required unique token
   identifier (jti)**. Reject tokens without jti for sensitive operations.
3. Query authoritative tenant membership and role status, scoped to tenant.
4. Query authoritative token/session revocation status by issuer and jti.
5. Invoke `enforce_identity_policy` with those trusted callbacks.
6. Only then authorize the HITL operation and enter the SQL transaction.

Never pass `lambda: True` as a production callback or derive membership
from client-supplied claims. Fail closed on timeouts, missing data or outages.
This PR deliberately does **not** wire the policy into live HTTP routes,
because no authoritative membership/revocation backend has been configured
or validated. Doing so without that dependency would either block all
requests or create a false sense of security.

Required before production: implement and test trusted backends, fail-closed
API wiring, token jti enforcement, audit events, end-to-end Postgres tests
and exact-SHA CI acceptance.
