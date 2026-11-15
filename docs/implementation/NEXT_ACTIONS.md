# Next actions

## Owner (blocking)
1. Review the draft PRs (aepx-core identity/UX, good-hour env wiring). Approve merge + deploy, or request changes.
2. Google Cloud Console → OAuth client (Web): redirect URI
   `https://auth.softwareequality.com/realms/aepx/broker/google/endpoint`; put the id/secret in the server `.env`
   as `AEPX_GOOGLE_CLIENT_ID` / `AEPX_GOOGLE_CLIENT_SECRET`.
3. Resend → add and verify `softwareequality.com` (SPF, DKIM, DMARC records); then set
   `AEPX_SMTP_FROM=no-reply@softwareequality.com` in `.env`.
4. Sign in once on production so signed-in flows can be verified.
5. Earlier, still open: Play upload of `aepx-play-0.3.0.zip`; `VSCE_PAT` / `OVSX_PAT` / `JB_MARKETPLACE_TOKEN`;
   `AEPX_UPLOAD_*`; AdSense unit IDs.

## Engineering (next draft PRs, in order)
1. P02-4 launcher status labels (available / beta / needs setup) driven by the module registry.
2. P05 provider error handling: classify 401/403/429/5xx/timeout, bounded retry with jitter, idempotency
   key so a retry never double-charges, user-facing messages.
3. P03 adversarial ACL/RLS suite (cross-tenant reads/writes, role escalation, path traversal) on local Postgres.
4. P09 release gate that refuses a release without production verification evidence.
5. P07 in-product plugin registry (signed manifests, capability grants, install/disable/uninstall; no host execution).
