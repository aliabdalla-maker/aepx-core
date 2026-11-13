# MCP exact-tool contract gate — offline only

`app.mcp_contract_gate.canonical_tool_call` is a pure pre-dispatch validator. It canonicalizes JSON arguments, enforces a 64 KiB payload limit, checks the tool allowlist and exact approved tool name, verifies SHA-256 of the approved arguments, and requires a printable idempotency key. It performs no network calls or side effects.

**Not yet integrated:** the governed worker does not call this validator; no MCP protocol client/server session or authenticated discovery has been proven. The adapter must obtain the approval digest and idempotency key from trusted tenant-scoped persistent records, never from the requester. SHA-256 alone is not an authorization credential. It must atomically consume a single-use approval and reserve a dispatch before invoking the provider. A remote provider must independently honor idempotency; unknown outcomes must be quarantined rather than replayed. Validate schema and destination policy, OAuth scopes, TLS and egress enforcement in isolated staging.

Keep external execution and gateway forwarding disabled. No production claim until real MCP integration, security tests and CI pass.

## Trusted approval/execution binding

The pure `bind_approved_mcp_dispatch` helper now requires matching tenant, run and approval IDs from a consumed approval and a reserved execution before building the exact MCP contract. Callers must fetch these records under trusted database credentials and ensure the dispatch reservation is atomically transitioned with cancellation/fencing checks. This helper does not lock rows, authenticate records, consume approvals or invoke MCP servers. The resulting data must never be accepted as a bearer authorization token.
