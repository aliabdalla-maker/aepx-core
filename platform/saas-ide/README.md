# AEP-X Hybrid SaaS IDE

Phase 1 implementation lives in this directory. See [Phase 1 setup](PHASE1-SETUP.md) and the [OCI London deployment plan](OCI-LONDON-DEPLOYMENT.md).

## Phase 1 source
- `backend/app/main.py`: FastAPI with verified OIDC RS256 access tokens, PostgreSQL tenant membership and role-based project/file endpoints
- `backend/migrations/001_phase1.sql`: PostgreSQL tenant row-level security and tenant-consistent workspace foreign keys
- `backend/tests/`: authentication/path smoke tests and PostgreSQL/OIDC integration tests
- `web/`: Next.js and Monaco browser editor with OIDC PKCE login and workspace persistence
- `.github/workflows/hybrid-ide-phase1.yml`: backend tests against PostgreSQL and frontend typecheck/build
- `monetization/`: AdSense and AdMob identifiers, with live ads disabled

## Security and deployment
No public deployment is authorised. A real OIDC provider, least-privileged PostgreSQL role, membership provisioning, successful CI and independent tenant-isolation verification are required before staging. The database tenant header selects an RLS scope; it is not proof of tenant membership. The authenticated subject must have an approved membership in that tenant.

Do not use the previous development API-key design: it has been replaced. Do not copy local credentials into GitHub. The OCI London Compute console remains a documented target, not an active deployment.

## Status
The source is committed to a **draft** pull request. Automated test results and end-to-end runtime behaviour must be verified from GitHub Actions and an actual staging environment before claiming readiness.
