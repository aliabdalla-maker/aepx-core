# Test evidence — branch `feat/p01-identity-ux` (2026-11-15)

All runs below were executed in this session; none are production runs.

| Check | Command / method | Result |
|---|---|---|
| Backend: new public endpoints | `pytest tests/test_public_meta.py tests/test_main.py` | 10 passed |
| Backend: full suite incl. PostgreSQL 16 integration (RLS, ACL, metering) | `pytest tests` against local Postgres with all migrations | 258 passed, 4 skipped |
| Web: unit tests | `vitest run` | 46 passed (39 existing + 7 new in `lib/signin.test.ts`) |
| Web: typecheck | `tsc --noEmit` | clean |
| Web: production build | `next build` | success |
| Keycloak setup, scenario A (nothing configured) | `keycloak-setup.sh` against Keycloak 26.0.7 started with `aepx-realm.json` | reset off, verifyEmail off, no IdPs, SMTP empty, TOTP policy + brute force on |
| Scenario B (Resend + Google + GitHub, secrets with `"` and `\`) | same | reset on, verifyEmail on (flag), Google trustEmail=true, GitHub trustEmail=false, SMTP stored (smtp.resend.com:465 SSL, user `resend`); **0 secret occurrences in script output**; login page shows Google, GitHub, Forgot password, Register |
| Scenario C (credentials removed) | same | IdPs deleted, SMTP cleared, reset off again |
| Reset link without a session | `GET /realms/aepx/login-actions/reset-credentials?client_id=aepx-ide-browser` | "Forgot Your Password?" form |
| Create-account button | auth request with `prompt=create` | registration form |
| Google button | auth request with `kc_idp_hint=google` | 303 to `/broker/google/login` |
| Signed-out UI, default options | headless Chrome against `next start`, API mocked | e-mail + create buttons only; reset explained; Operations "Sign in to see operations." with no Refresh; Save tooltip; `build 0f9044c` |
| Signed-out UI, Google + reset enabled | same, API reports a different SHA | Google button first; working reset link; footer `web 0f9044c · api abcdef0` in warning colour |
| Fail-safe | page built without an allowed API origin (CSP blocks the call) | falls back to e-mail-only buttons; nothing broken shown |

Not verified: anything in production; any signed-in flow; real e-mail delivery; real Google OAuth.
