# HITL OIDC verifier foundation

The governance service now has a fail-closed JWT verifier helper. Configure `HITL_OIDC_ISSUER`, `HITL_OIDC_AUDIENCE` and `HITL_OIDC_JWKS_URL` for a trusted HTTPS OIDC provider. JWKS must share the issuer hostname. JWT signature is validated with RS256 or ES256, with mandatory exp/iat/iss/aud/sub claims. Tenant ID and roles are read only from verified claims, then converted into a `VerifiedPrincipal`.

**Security limitation:** This module is not connected to HTTP routes. The identity provider must be configured to issue authoritative `tenant_id` and `roles` claims, enforce tenant membership and revocation policy, and publish an approved JWKS endpoint. Claim semantics, token replay policy, audience, clock skew, key rotation and IdP threat model need integration tests. Do not expose privileged HITL operations until that integration and real PostgreSQL RLS tests pass.

Next: FastAPI request/approve/consume routes using the verified principal; non-owner DB credentials; actual PostgreSQL migrations and two-tenant integration tests; idempotent outbox dispatcher; governed MCP/CrewAI/RAG; OCI Always Free staging acceptance. No OCI resources were changed by this PR.
