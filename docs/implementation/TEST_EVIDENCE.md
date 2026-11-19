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
| Create-account button | auth request with `prompt=create` | **Correction (2026-11-15 evening):** Keycloak 26.0.7 ignores `prompt=create` and shows the sign-in page (the earlier check matched the login page's own "Register" link). Fixed in the assistant/import PR by sending this button to `/protocol/openid-connect/registrations`, verified to show `#kc-register-form`. |
| Google button | auth request with `kc_idp_hint=google` | 303 to `/broker/google/login` |
| Signed-out UI, default options | headless Chrome against `next start`, API mocked | e-mail + create buttons only; reset explained; Operations "Sign in to see operations." with no Refresh; Save tooltip; `build 0f9044c` |
| Signed-out UI, Google + reset enabled | same, API reports a different SHA | Google button first; working reset link; footer `web 0f9044c · api abcdef0` in warning colour |
| Fail-safe | page built without an allowed API origin (CSP blocks the call) | falls back to e-mail-only buttons; nothing broken shown |

Not verified: anything in production; any signed-in flow; real e-mail delivery; real Google OAuth.

## Release 1248102 in production (2026-11-15 20:06 UTC, deployed via good-hour #22)
| Check | Result |
|---|---|
| `GET /health` | 200 `{"status":"ok"}` |
| `GET /api/v1/version` | `release_sha` 1248102037c98625f5657d95e9f61e8a0c365f77 (server `.env` does not override the pin) |
| Footer | `build 1248102`, no web/API drift |
| Signed-out home | Sign in with e-mail, Create an account, honest password-reset note |
| Operations (signed out) | "Sign in to see operations.", no Refresh button |
| Sign in with e-mail | reaches the Keycloak sign-in page |
| Signed-in create/save/reopen | **not verified in production** (needs the owner's test account) |

## Assistant, import and password policy (branch feat/assistant-import-passwordpolicy)
| Check | Method | Result |
|---|---|---|
| Unit tests | `vitest run` | 59 passed (13 new: help parsing/search, AI task limits, zip reader on a real archive, import planning) |
| Typecheck / build | `tsc --noEmit`, `next build` | clean / success |
| Password policy | `keycloak-setup.sh` on Keycloak 26.0.7 with the production realm, then admin API | 7-char and no-upper-case passwords rejected; reuse of the last password rejected; compliant password accepted. Note: `notUsername` blocks a password equal to the username, not one containing it (help text says so). |
| End-to-end, local stack (Keycloak HTTPS + API on PostgreSQL 16 + production web build, headless Chrome) | `/tmp/e2e.py` | **14/14**: assistant answers from help signed out; Create an account opens registration; weak password rejected at registration; e-mail sign-in; project created; existing README not overwritten by default; .zip import (2 text files, binary + node_modules skipped); saved; reload + reopen keeps the edit; footer build; assistant uses module context; AI-off reason shown |
| Ask AI end-to-end | — | **not verified**: needs the isolated metered worker (not run locally). It uses the existing create/decide/enqueue/run endpoints unchanged. |

## File and project operations (branch feat/ide-file-ops)
| Check | Method | Result |
|---|---|---|
| API | `pytest tests/test_file_ops.py` on PostgreSQL 16 | 7/7: file rename keeps content + history (delete/save versions); folder move moves only that folder; overlapping move (a/x -> a) succeeds; conflict 409, same name 400, into-itself 400, traversal 400, missing 404 with nothing changed; folder delete versioned and scoped; media editor limited to media paths, viewer/other tenant refused; `file.move` audited. Full backend suite 265 passed. |
| Web | `vitest` | 64 passed (5 new: move mapping, tabs keep unsaved edits, client-side rename validation, search with line numbers and caps) |
| End-to-end, local stack (Keycloak HTTPS + API + production web build, headless Chrome) | `/tmp/e2e2.py` | **12/12**: create + save files; search finds `src/lib/util.py:2` and opens it at line 2; rename file (tab follows); move folder `src/lib` -> `pkg/lib`; rename onto an existing file refused; new folder; delete folder; state persists after reload; rename project; archive; restore |

## Sandboxed code execution (branch feat/sandbox-runner) — not enabled in production
| Check | Method | Result |
|---|---|---|
| Runner validation, flags, HMAC, replay | `pytest runner/tests` (no Docker part) | pass |
| Real containers (runc, local) | `pytest runner/tests` with a local image built from the workspace's own Python/Node (Docker Hub is blocked in this workspace) | 12/12: Python + Node output and exit codes, multi-file imports, **no network**, **read-only project and root**, **uid 65534**, **10 s timeout kills the container**, **memory limit**, **process limit**, output cap. Two real bugs found and fixed: `-I` broke multi-file imports; `/tmp` was not writable by the sandbox user. |
| API endpoint | `pytest tests/test_execution.py` on PostgreSQL 16 | 9/9: off by default with reason; misconfigured runner stays off; runs saved files and audits `code.run`; unsaved/unsupported/path-traversal refused; viewer refused; other tenant refused; rate limit; honest runner errors; runner URL must be HTTPS or explicitly allowed private HTTP |
| Full chain | API -> HMAC-signed request -> runner app -> real container | Python with local import printed 42 with exit code 5; Node printed `node 42`; forged signature refused (401) |
| gVisor | CI job `runner` (PR #412) on GitHub runners: runsc 20261109 installed, same 12 tests | **12/12 under runsc**; guest kernel `4.19.0-gvisor` vs host `7.0.0-1014-aws`, so runs really are inside gVisor; production runner image builds |
| Production | — | **not enabled**: `IDE_CODE_EXECUTION_ENABLED` stays false until a gVisor host passes the setup self-test and the acceptance run |
