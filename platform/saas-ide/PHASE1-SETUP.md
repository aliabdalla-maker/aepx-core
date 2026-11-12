# Phase 1 — OIDC, PostgreSQL and Monaco IDE

Status: source implementation committed, **not deployed or verified end-to-end**.

## Prerequisites
- PostgreSQL 15+ database and two distinct database roles: a privileged **migration role** and a least-privileged **runtime role**.
- OIDC identity provider with a public browser client supporting Authorization Code + PKCE and an API access-token audience.
- Python 3.11+, Node.js 20+, npm.
- Configure the identity provider to issue **RS256 JWT access tokens** for the API audience and register `http://localhost:3000/callback` for local development.
- Register one or more tenant memberships using a trusted administrative provisioning process; **do not** let users self-assign membership or tenant roles.

## Database
Apply `backend/migrations/001_phase1.sql` as the migration role. Grant the runtime role SELECT on `ide_memberships`, and SELECT/INSERT/UPDATE on `ide_projects` and `ide_workspace_files`. The runtime role must not own these tables, have BYPASSRLS, or use superuser credentials. Audit grants and verify that RLS applies under the actual runtime role.

**Important:** RLS uses the transaction-local `ide.tenant_id` setting. The API sets this for every database request before the membership lookup; the membership check then verifies the token subject belongs to that tenant. Never grant the runtime role INSERT/UPDATE/DELETE on memberships. A separate privileged administrator must provision memberships.

Example administrative provisioning (substitute approved values, do not run in production without change control):
```sql
INSERT INTO ide_memberships (tenant_id, subject, role)
VALUES ('demo-tenant', 'oidc-subject-from-provider', 'owner');
```

## API
```bash
cd platform/saas-ide/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export IDE_DATABASE_URL='postgresql+psycopg://ide_runtime:password@localhost:5432/ide'
export IDE_OIDC_ISSUER='https://your-provider.example.com/realms/ide'
export IDE_OIDC_JWKS_URL='https://your-provider.example.com/realms/ide/protocol/openid-connect/certs'
export IDE_OIDC_AUDIENCE='ide-api'
export IDE_WEB_ORIGIN='http://localhost:3000'
uvicorn app.main:app --port 8090
python -m pytest tests -v
```

The JWKS URL must be the identity provider's **verified HTTPS signing-keys endpoint**. Never disable JWT verification. Do not place database credentials in source control.

## Browser IDE
```bash
cd platform/saas-ide/web
cp .env.example .env.local
# Edit issuer, client ID and tenant to match registered OIDC settings
npm install
npm run typecheck
npm run build
npm run dev
```
Open http://localhost:3000. Sign in, create a project, add a file, edit it and save. The browser sends a verified OIDC access token to the API; the API checks tenant membership independently.

## Acceptance criteria
- [ ] Token with invalid signature, issuer, audience or expiry is rejected.
- [ ] Missing membership is denied, even with a valid access token.
- [ ] Viewer cannot create projects or save files.
- [ ] A member of tenant A cannot list/read/write tenant B projects.
- [ ] RLS blocks cross-tenant queries under the runtime database role.
- [ ] Project and file contents survive API restart.
- [ ] Browser login callback, editor load and save work end-to-end.
- [ ] npm typecheck/build, pytest and migration integration tests pass.
- [ ] No production deployment before independent security review.

## Limitations and next work
- This is a functional IDE shell, not a code execution environment.
- Membership provisioning is an administrative operation; self-service onboarding and organisations UI are not implemented.
- File writes are last-write-wins; concurrency control and file history are future work.
- The browser holds its token in session storage; for production, assess a secure backend-for-frontend session model.
- PostgreSQL RLS requires real-database integration testing before production use.
- OCI London is a documented target only; no deployment performed.
