# Phase 2.8 release gates — NOT production approved

## Implemented and under CI
- PostgreSQL integration tests simulate approved job → fenced claim → budget reservation → offline mock response → conservative settlement → persisted result.
- Failure-boundary tests simulate a dead worker before reservation, after reservation, after provider response, and after settlement by expiring the lease and quarantining it. Stale results and replay are rejected. These are **simulated process loss**, not OS process-kill chaos tests.
- Conservative full-envelope settlement is now a single locked transaction to prevent settlement/reconciliation double charging.
- Prior suites cover OIDC issuer/audience/signature/expiry, tenant membership/RBAC, FORCE RLS, cancellation fencing, concurrent MCP single-use consumption, DNS rebinding and offline Docker network namespace.

## Critical release blockers
- **Production egress enforcement not delivered.** The test-only pinned-IP HTTPS client does not intercept provider SDK or MCP sockets. Flags and URL validation do not prove enforced network isolation. Keep provider and MCP external execution disabled; require reviewed OS-level no-direct-egress rules and a proxy that revalidates every DNS/IP/TLS connection, denies redirects, and tests all SDK bypass paths.
- **Provider evidence not verified.** Mock receipts test bookkeeping only. Production requires authenticated provider billing ingestion, immutable provider request IDs, duplicate detection across providers, disputed usage handling and alerting. The operator reconciliation function currently trusts supplied evidence.
- **True crash injection and mock worker subprocess execution not delivered.** Integration tests simulate crash boundaries in DB transactions, not SIGKILL of an isolated subprocess with actual mock inference adapter.
- **Full CI and deployment readiness** require passing repository-wide checks, staging restore and rollback rehearsal, penetration review, explicit owner sign-off, least-privilege secret rotation and incident on-call procedures.

## Operator checklist
1. Verify branch and draft PR #25; confirm external execution flags are absent/false.
2. Run dedicated Hybrid IDE PostgreSQL tests and repository-wide CI.
3. Check tenant audit, budget spent/reserved invariants, and unresolved reservations.
4. Never retry ambiguous provider calls; quarantine expired leases and reconcile against independent provider evidence.
5. Rehearse backup restore, rollback, credential revocation and network kill switch in staging before any release approval.

No merge, deployment or external execution enablement is authorized by this document.
