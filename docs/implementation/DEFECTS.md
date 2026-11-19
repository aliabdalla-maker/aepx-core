# P00 — defects found on the live signed-out IDE, with root causes

Source: owner screenshots of https://ide.softwareequality.com (signed out) and a live probe of the
production Keycloak login page on 2026-11-15 (`social: []`, `forgot: false`, `register: true`).

| # | Symptom (live) | Root cause | Fix in this branch | Still needed |
|---|---|---|---|---|
| D1 | No "Sign in with Google" | `AEPX_GOOGLE_CLIENT_ID/SECRET` not set in the server `.env`, so `keycloak-setup` creates no Google identity provider | Welcome shows Google only when `GET /api/v1/auth-options` says it is configured; setup script verified to add/remove it | **Owner:** create a Google OAuth client (redirect `https://auth.softwareequality.com/realms/aepx/broker/google/endpoint`) and put id/secret in `.env` |
| D2 | No "Forgot password?" | Realm has `resetPasswordAllowed: false` and no SMTP server | Setup script configures SMTP (explicit `AEPX_SMTP_*` or Resend relay) and turns reset on **only** when mail is configured | **Owner:** verify softwareequality.com in Resend (SPF/DKIM/DMARC DNS) and set `AEPX_SMTP_FROM` |
| D3 | Signed-out home is a bare "Welcome to AEP-X" with no way in except the header button | Empty state had no signed-out branch | New signed-out welcome: Google (if enabled), e-mail sign-in, Create account, Forgot password (or an honest explanation), Terms/Privacy | — |
| D4 | Operations says "No execution metrics" when signed out | Panel rendered the empty-counts text for every non-success state, and swallowed 403/5xx into one generic message | Distinct signed-out / loading / denied / unavailable / failed / empty states; Refresh hidden when signed out | Signed-in production check |
| D5 | Save is greyed out with no explanation | Disabled button had no title/description | Tooltip + `aria-description` saying why | — |
| D6 | No way to tell which build is live | No release identity exposed | `GET /api/v1/version` (`IDE_RELEASE_SHA`) + web build SHA in status bar, flagged when they differ | good-hour PR to pass the SHA |
| D7 | GitHub sign-in (when enabled) trusted e-mail for account linking | `trustEmail=true` for every provider | GitHub now `trustEmail=false`; Google stays `true` (Google issues verified addresses) | — |
| D8 | Header "Sign in" button disabled when OIDC env missing, with no reason | Button rendered disabled | Hidden when not configured; welcome explains sign-in isn't set up | — |

Not reproduced as defects: Team "Sign in to manage your team", and Knowledge/Studio/Agents "open a project"
messages are correct signed-out states.
