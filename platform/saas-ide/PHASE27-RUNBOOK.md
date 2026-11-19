# Phase 2.7 security validation and incident runbook (draft)

## Default-deny execution
External provider calls remain OFF unless `IDE_EXTERNAL_EXECUTION_ENABLED=true` and separate governed-worker/egress/reconciliation gates are set. **Do not enable** in production based on these tests. `egress27.gateway_get` is a test-only HTTPS GET client with strict hostname allowlist, public-IP DNS checks, one pinned address per request, TLS SNI/certificate hostname validation, no redirects and a 1 MiB response cap. It is NOT wired into provider SDKs or MCP and is NOT a production outbound firewall. Docker CI independently verifies a network-disabled namespace. DNS rebinding is tested by injecting hostile resolver responses.

## Deployment prerequisites (not performed)
1. Review migrations 001–006 and back up PostgreSQL with restore rehearsal; run under a migration administrator, never runtime role.
2. Configure OIDC issuer, audience and JWKS; confirm RLS FORCE and non-BYPASSRLS runtime role. Separate service identities for migration, API and worker.
3. Require enforced worker network namespaces with no direct internet, a dedicated outbound gateway with verified DNS/IP policies, destination allowlists, TLS verification and blocked redirects. Confirm all SDKs and MCP clients cannot bypass it.
4. Add authenticated provider usage receipts and reconciliation signatures; alert on discrepancies and unresolved reservations.
5. Run staging chaos tests, provider contract tests, complete CI, review secret rotation and incident access; obtain explicit change approval.

## Incident: crashed worker / expired lease
Do not re-dispatch ambiguous provider calls. Quarantine expired leases using `recovery25.quarantine_expired` under a separately authenticated, tenant-authorized operator. Check `tenant_metrics` for unresolved reservations. Query provider billing/usage by provider request ID; confirm no duplicate side effects. Use `reconcile` with externally verified unique reference, bounded actual usage and an auditable operator identity. Escalate charges exceeding the reserved envelope. Preserve immutable audit and provider evidence. Do not release unknown charges automatically.

## Incident: suspected SSRF / DNS rebinding
Disable external execution at the network firewall first, revoke provider credentials, preserve gateway DNS/IP/TLS logs and tenant audit. Verify no metadata endpoint or private network access. Rotate affected secrets and isolate worker nodes. Restore only after reviewed policy and negative tests.

## Rollback
Keep the feature branch unmerged. If a staging rollout ever occurs, disable worker execution first, drain/quarantine leases, reconcile outstanding spend and restore the prior application revision. Do not drop migration 006 while reconciliation evidence exists. Database rollback requires a separately tested forward migration and verified backup restore.

## Verification status and known gaps
Test coverage includes parallel PostgreSQL claim/approval races (Phase 2.6), mock DNS rebinding, pinned TLS socket destination, crash-after-reservation quarantine, mock billing reconciliation and OIDC/RLS/RBAC tests from earlier phases. The gateway is **not** integrated into production adapters; no live provider calls, actual provider billing evidence verification, signed receipts, injected process kill at every transaction boundary, or full mock-provider end-to-end lifecycle has been demonstrated. These are release blockers. No merge, deploy or execution enablement.
