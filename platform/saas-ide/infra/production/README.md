# Hosted IDE: production (ide.softwareequality.com)

The hosted AEP-X Agentic IDE runs on the Oracle Cloud server that already serves
goodhour.shop and softwareequality.com. The server's Docker stack lives in the
`aliabdalla-maker/good-hour` repo (`docker-compose.prod.yml`, `deploy/Caddyfile`).
The server pulls that repo every 2 minutes and rebuilds, and the IDE services build
straight from this public repo at the commit pinned in `AEPX_IDE_REF`.

| Address | Service | Source |
|---|---|---|
| https://ide.softwareequality.com | `ide-web` (Next.js) and `ide-api` (FastAPI, `/api/*`, `/health`) | `web/`, `backend/` |
| https://auth.softwareequality.com | `keycloak`, realm `aepx` | `infra/production/keycloak.Dockerfile` |
| internal only | `ide-db` (PostgreSQL 16 + pgvector) | `pgvector/pgvector:pg16` |

## First start

1. DNS: add A records `ide` and `auth` for softwareequality.com pointing at
   `143.47.255.104`. Caddy issues HTTPS certificates once they resolve.
2. Nothing else is required. `ide-secrets` generates the database and Keycloak
   admin passwords into the `ide_secrets` volume. `ide-migrate` creates the roles,
   the Keycloak database and the IDE schema (each migration once; the record is
   kept in `aepx_schema_migrations`).

Keycloak admin console: https://auth.softwareequality.com/admin. The user is
`admin`; the password is read on the server with
`docker compose -f docker-compose.prod.yml exec keycloak cat /run/ide-secrets/keycloak_admin`.

## Sign-in options

- Email and password sign-up is on from the start. Each new user gets a private
  workspace on first sign-in (`POST /api/v1/workspace`, migration
  `010_personal_workspaces.sql`) and a 30-day trial.
- Google and GitHub buttons appear once their OAuth client details are in the
  server's `.env`, and `keycloak-setup` runs on the next deploy:
  - `AEPX_GOOGLE_CLIENT_ID` / `AEPX_GOOGLE_CLIENT_SECRET`. Google Cloud console:
    create an OAuth client of type "Web application" with redirect URI
    `https://auth.softwareequality.com/realms/aepx/broker/google/endpoint`.
  - `AEPX_GITHUB_CLIENT_ID` / `AEPX_GITHUB_CLIENT_SECRET`. GitHub: Settings >
    Developer settings > OAuth Apps, callback URL
    `https://auth.softwareequality.com/realms/aepx/broker/github/endpoint`.
- Password reset and email verification need an SMTP server. Configure one in the
  realm's Email settings, then turn them on.

## Subscriptions

Web subscriptions (£4.99/month through Stripe) switch on when these are set in
`.env`: `AEPX_IDE_STRIPE_SECRET_KEY`, `AEPX_IDE_STRIPE_PRICE_ID` (a recurring
£4.99 GBP price) and `AEPX_IDE_STRIPE_WEBHOOK_SECRET` (a webhook to
`https://ide.softwareequality.com/api/v1/billing/stripe/webhook`). Until then the
plan banner shows the trial and the free tier.

## AI agents

They are off: `IDE_EXTERNAL_EXECUTION_ENABLED=false`. Turning them on needs the
governed worker, the network egress gateway and provider-spend reconciliation
described in `../../PHASE27-RUNBOOK.md`. Those are release blockers, not settings.

## Upgrade and roll back

Set `AEPX_IDE_REF` in the good-hour compose file (or the server's `.env`) to the
new full commit SHA, then push to good-hour `main`. To roll back, set the previous
SHA. Migrations only move forward, so restore a database backup if a migration
must be undone.
