# Deployment readiness — identity & signed-out UX

**Status: not deployed. Ready for owner review as a draft PR. Merge and deploy require explicit owner approval.**

## What deploying this changes
- Keycloak realm `aepx` on each deploy: SMTP from env, reset/verify-email gated on mail, TOTP policy,
  brute-force backoff, GitHub `trustEmail=false`. With today's `.env` (no Google, no `AEPX_SMTP_FROM`)
  the visible effect is **none** on the login page; reset stays off until mail is configured.
- IDE API: two new public GET endpoints returning booleans and a commit SHA. No secrets, no DB access.
- IDE web: new signed-out welcome, Operations states, Save hint, release label.

## Required server environment (good-hour, companion draft PR)
| Variable | Service | Purpose |
|---|---|---|
| `AEPX_SMTP_FROM` | keycloak-setup | Sender on a Resend-verified domain; enables mail + reset |
| `RESEND_API_KEY` (already set) | keycloak-setup | SMTP relay password |
| `AEPX_VERIFY_EMAIL` (optional) | keycloak-setup | Require e-mail verification for new accounts |
| `AEPX_GOOGLE_CLIENT_ID/SECRET` | keycloak-setup | Google button |
| `IDE_AUTH_GOOGLE_ENABLED`, `IDE_AUTH_PASSWORD_RESET_ENABLED`, … | ide-api | Derived in compose from the above |
| `IDE_RELEASE_SHA` / build arg `NEXT_PUBLIC_RELEASE_SHA` | ide-api / ide-web | `AEPX_IDE_REF` |

## Rollback
Revert the PR and redeploy. Realm settings revert by re-running the previous `keycloak-setup`
(it overwrites the same fields); identity providers and SMTP are re-derived from `.env`.

## Production verification to do after an approved deploy
1. `GET /api/v1/version` returns the deployed SHA; status bar shows `build <sha>` with no drift.
2. Signed-out home shows only working options; Operations shows "Sign in to see operations."
3. After Resend verification: request a reset for a test account and receive the e-mail.
4. After Google client: "Continue with Google" completes and lands in the workspace.
