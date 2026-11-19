# Phase 2.2 — draft secure execution hardening

Delivered: tenant-RLS PostgreSQL jobs and leases, idempotent enqueue, exact tool argument SHA-256 approvals, opt-in worker Docker reference, budget policy primitives, network URL/IP checks and tests.

**Security boundary:** Queue recovery is at-least-once; it is not exactly-once external execution. A lease-expired worker may still finish an external call. Do not enable execution until a fencing-token protocol, isolated executor with killable subprocess deadlines, per-tenant spending ledger and upstream provider idempotency have been verified. Current budgets are validation primitives, not metered enforcement. Network URL/IP validation alone does not prevent DNS rebinding or proxy bypass. The example container uses `network_mode: none`, which intentionally prevents DB and LLM access; a future isolated worker requires an audited egress proxy and private database network with explicit policy.

Apply migrations 001, 002, 003 and 004 in order with privileged role. Runtime grants: SELECT/INSERT/UPDATE on `ide_agent_jobs` and `ide_tool_approvals`; worker role should have only necessary tenant-scoped privileges. All table owners and migration users must be separate from runtime identities.

Exact tool approval is persisted and single-use; **the existing MCP adapter is not yet wired to consume the approval**. Never expose unrestricted tool invocation. Approval of a run does not approve any MCP tool call.

All external flags remain false by default. Do not merge or deploy until CI and security reviews complete.
