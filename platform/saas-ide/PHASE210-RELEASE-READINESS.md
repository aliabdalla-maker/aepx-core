# Phase 2.10 security integration — draft / NOT production-ready

## Code changes
- Provider SDK, MCP and CrewAI dispatch now fail closed unless `IDE_NETWORK_ISOLATION_ATTESTED=true` and the prior execution/egress gates are present. **This is an application-level attestation check; it does not prove or enforce network isolation.** The variable must never be set without independent infrastructure verification.
- Test-only pinned destination preflight rejects HTTP, private IPs, ambiguous DNS, non-443 ports, userinfo, nonallowlisted domains and DNS rebinding. The preflight is not connected to actual provider SDK transports.
- Previous Phase 2.9 tests exercise PostgreSQL lease-holder SIGKILL and quarantine, authenticated mock receipts, RLS/tenant checks, owner/admin alerts and network-disabled Docker tests.

## Mandatory production blockers
1. **Enforced SDK/MCP egress:** deploy a separate egress gateway with OS-enforced no-direct-internet policy on the actual provider/MCP worker namespace. Verify provider SDKs use it, block alternate sockets, metadata IP, redirects, DNS rebinding and proxy bypass. Application flags are insufficient.
2. **Billing:** obtain independent mock-provider service evidence from a separately authenticated process, then implement real provider billing APIs with immutable request IDs and dispute workflows. Locally signed HMAC mock receipts do not constitute independent evidence.
3. **Fault injection:** extend SIGKILL on actual leased workers to reservation, dispatch, result persistence and settlement, verify no replay or double debit after restart.
4. **Security:** complete OIDC/RBAC/RLS/MCP/cancellation adversarial suites and security review of all entrypoints.
5. **Release:** dedicated and repository-wide CI green, restore/rollback rehearsal, SRE incident owner, secrets rotation and formal security approval.

## Staging checklist
- External execution flags remain false. Do not set `IDE_NETWORK_ISOLATION_ATTESTED` without a documented audited firewall.
- Record exact CI SHA, failed tests, signed evidence source, tenant isolation and budget invariants.
- Simulate network cutoff and rollback in a separate staging environment; do not execute in production.
- On provider incident: stop egress, quarantine leases, preserve evidence, reconcile manually and do not automatically replay ambiguous calls.

**Draft PR #25 only. No merge, deploy or live external execution.**
