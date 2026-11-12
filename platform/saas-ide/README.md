# AEP-X Hybrid SaaS IDE — initial implementation

This folder is a **development-only** foundation for the hybrid IDE.
It does not claim to be a finished SaaS product.

## Implemented
- FastAPI project metadata endpoints and OpenAPI schema
- SQLite persistence for local development
- Tenant-scoped project create/list/get
- Development API key required; missing key fails closed
- Production mode refuses requests until real OIDC is integrated
- Automated tenant isolation and authentication regression tests

## Not implemented
OIDC, RBAC, multi-user membership, Postgres, Monaco frontend,
AEP-X execution integration, MCP, RAG, LLM routing, sandboxes,
GitHub PR automation, Stripe entitlements and OCI deployment.

## Run locally

```bash
cd platform/saas-ide/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export IDE_ENV=development
export IDE_DEV_API_KEY=replace-with-a-long-random-local-secret
export IDE_DB_PATH=./ide.sqlite3
uvicorn app.main:app --reload --port 8090
python -m pytest tests -v
```

PowerShell: use `.venv\\Scripts\\Activate.ps1` and `$env:IDE_DEV_API_KEY="..."`.
The API documentation is at http://localhost:8090/docs.

**Security note:** The development API key is shared across tenants, so it
does **not** establish tenant identity against malicious clients. It is suitable
only for isolated local testing. Never expose this API publicly; replace
the development boundary with validated OIDC subject, issuer, audience,
roles and tenant membership, plus Postgres RLS, before any external pilot.

## Next milestone
Introduce production-grade OIDC and tenant membership checks, PostgreSQL
migrations and a minimal Next.js + Monaco workspace UI. Only then integrate
AEP-X governed agent execution behind isolated workers.
