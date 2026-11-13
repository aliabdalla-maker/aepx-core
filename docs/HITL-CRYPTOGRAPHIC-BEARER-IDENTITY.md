# Cryptographic bearer-to-identity boundary

`verify_bearer_identity` validates a bearer token using pinned RS256,
issuer, audience, expiry, issued-at, not-before, subject, jti and tenant
claims. It then passes the verified claims to the PostgreSQL identity
policy, which requires active tenant membership, a healthy recent IdP
snapshot, and absence from the revocation table.

**Not wired to live HTTP endpoints.** Production integration must call this
function before any HITL mutation and must use a restricted DB read role.
The shared JWT PR #73 remains open; reconcile the duplicated verification
code before enabling routes. PyJWKClient fetches keys over HTTPS but this
module does not independently pin resolved IPs or disable redirects; review
egress/SSRF protections before production use. Tests use injected mocks and
do not establish real cryptographic or PostgreSQL end-to-end acceptance.

No merge, migration, deployment or external execution is authorized.
