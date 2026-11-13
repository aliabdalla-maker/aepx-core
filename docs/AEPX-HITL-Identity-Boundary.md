# HITL identity boundary

`hitl_authz.py` defines a fail-closed authorization contract for request, approval and consumption. It rejects cross-tenant access, missing roles, unverified object types and self-approval. **This is not authentication**: `VerifiedPrincipal` must be constructed only by a trusted upstream adapter after verifying a signed access token's issuer, audience, signature, expiry, tenant membership and role claims. It is not safe to construct this object from user-supplied headers or JSON. The module is not yet wired to HTTP routes or PostgreSQL operations.

## Remaining acceptance gates
1. Implement a tested JWKS/OIDC verifier with fail-closed key rotation, issuer/audience and tenant membership checks.
2. Add request/decision/consume FastAPI endpoints that depend on the verifier, with non-owner PostgreSQL roles and transaction-local RLS.
3. Run PostgreSQL integration tests against real concurrent sessions and two tenants, including the outbox and migrations.
4. Run a real dispatcher with bounded retries, durable dead-letter handling and idempotent MCP consumers.
5. Implement supervised CrewAI, persistent tenant-scoped RAG, monitoring, backup/restore drills and OCI Always Free staging acceptance.
