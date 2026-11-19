# Phase 2.9 security enforcement — draft, not approved for production

## Added
- Offline HMAC-authenticated mock billing receipts, canonical serialization, strict type checks, tenant binding, tamper detection and duplicate ledger rejection. **Not provider-signed production evidence.**
- POSIX SIGKILL test terminates a real subprocess with no credentials; this only proves process termination, not atomic database recovery at every boundary.
- Tenant-scoped read-only alert evaluator reports failed jobs, unresolved reservations and spend threshold. Caller must authenticate/authorize tenant; not exposed as an API.
- Existing Phase 2.7 pinned-IP HTTPS GET test gateway, DNS rebinding tests, Docker `--network none` CI and Phase 2.8 PostgreSQL recovery tests remain in place.

## Blockers
1. Production provider SDK and MCP egress is **not** enforced by a network gateway. No application-level URL validator can prevent bypass by arbitrary SDK sockets. Enforce OS/container network policy: deny all outbound except a dedicated inspected gateway; allow gateway DNS only, block private/metadata addresses after resolution, pin TLS destination and forbid redirects. Verify bypass attempts from every SDK in a staging namespace. Do not set `IDE_EXTERNAL_EXECUTION_ENABLED=true`.
2. No real provider-authenticated billing records. HMAC mock key is a test fixture, not independent attestation. Integrate provider billing API with verifiable request IDs and independently obtained usage before live operation.
3. SIGKILL is not yet injected into an actual leased worker with PostgreSQL fault checkpoints. Existing DB crash-boundary tests simulate process loss and quarantine, rather than demonstrating it end-to-end.
4. Alert evaluator is not an authenticated endpoint or monitoring pipeline. Require authorization checks, paging, retention and incident ownership.
5. Full repository CI, staging rollback rehearsal, independent security review and release approval are required.

## Incident / rollback
Keep execution disabled. On suspected SSRF, revoke outbound routes at the network firewall, rotate tokens and preserve logs. On expired leases, quarantine rather than replay; verify provider usage independently and reconcile reservations under tenant-authorized operator control. Roll back application revisions only after draining workers and preserving reconciliation evidence; rehearse database restoration before deployment.

**Do not merge or deploy draft PR #25.**
