# Trusted operator identity boundary

The `hitl_operator_identity.operator_verifier` factory provides an injectable
RBAC decision for `reconcile_remote(..., verify_operator=...)`.

Only construct `VerifiedOperator` inside trusted authentication middleware
**after** verifying OIDC token signature against issuer JWKS, allowed signing
algorithm, exact issuer and audience, expiry/not-before, tenant membership,
revocation policy and the authenticated subject. Never build it directly from
request JSON, user-supplied headers, decoded unverified JWT payloads or LLM
output. The `authenticated` boolean is an assertion by the upstream trusted
middleware, **not cryptographic proof**.

The adapter checks exact tenant, subject/reviewer, permission, issuer,
audience and expiry. It is deliberately independent of the separate provider
evidence verifier. Both must return exactly true for reconciliation.

Production OIDC middleware and provider verification remain unimplemented;
this change adds a reusable authorization policy, not end-to-end identity.
Do not use the unit-test identities or static-true verifiers in production.
