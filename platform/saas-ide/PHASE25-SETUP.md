# Phase 2.5 security/recovery hardening — draft only

New migration 006 introduces tenant-RLS reconciliation evidence. `recovery25.quarantine_expired` marks expired leased jobs failed, increments fencing tokens, and emits tenant audit records. It deliberately does **not** retry external calls: delivery and provider billing may be ambiguous. `recovery25.reconcile` accepts operator-supplied provider reference, usage and actor, updates reserved/spent balances atomically, records unique evidence and audits reconciliation. `tenant_metrics` exposes tenant-scoped queue, budget and unresolved-reservation counts. None of these functions is exposed as an unauthenticated HTTP route.

Reconciliation must be performed only after independently verifying provider billing records and authenticating/authorizing the operator. Usage above the reservation is rejected for manual investigation. There is no automated trusted provider usage ingestion or independent evidence verification yet.

`egress25.validate_https_destination` rejects non-HTTPS URLs, credentials, fragments, disallowed hosts and known non-public IPs. This is a **preflight validation helper only**, not enforceable network isolation; DNS rebinding, redirect handling, SDK proxy bypass and actual socket destinations require a dedicated outbound proxy/firewall policy with DNS/IP checks. The worker remains disabled by default. Do not set `IDE_EGRESS_GATEWAY_VERIFIED=true` until independently verifying infrastructure-level egress restrictions.

Tests cover quarantine/reconciliation, stale worker rejection, RLS and SSRF preflight. True multi-process concurrent claims, concurrent MCP approval consumption, worker-crash injection, provider-billing reconciliation and end-to-end gateway enforcement remain release blockers.

No merge, deployment or external execution authorization.
