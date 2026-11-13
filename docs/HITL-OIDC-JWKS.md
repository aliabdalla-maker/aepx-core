# OIDC JWT verification for HITL operators

`app.hitl_oidc_auth.verify_oidc_operator` validates an RS256-signed JWT
against a server-configured HTTPS JWKS URL and exact issuer/audience, plus
exp/iat/nbf/sub, tenant UUID and permission claims. It returns a
`VerifiedOperator` for the existing `operator_verifier` policy.

**Security boundary:** only trusted service configuration may supply issuer,
audience, JWKS URL and tenant/permission claim names. Never derive them from
the incoming JWT or request parameters. Keep outbound JWKS requests restricted
by egress allowlist and prohibit redirects to untrusted endpoints at the
network boundary. JWKS cache lifetime is 300 seconds.

The caller must also implement revocation/session termination, key rotation
operations, tenant membership lookup, rate limiting, replay policy for
sensitive actions and an authenticated API entrypoint. This module is not
wired to an HTTP route or provider evidence verifier. Do not treat the
presence of this module as production-ready authentication.

Tests use generated local RSA keys, no external identity provider calls.
