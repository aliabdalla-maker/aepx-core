# MCP exact-tool contract gate — offline only

`app.mcp_contract_gate.canonical_tool_call` is a pure pre-dispatch validator. It canonicalizes JSON arguments, enforces a 64 KiB payload limit, checks the tool allowlist and exact approved tool name, verifies SHA-256 of the approved arguments, and requires a printable idempotency key. It performs no network calls or side effects.

**Not yet integrated:** the governed worker does not call this validator; no MCP protocol client/server session or authenticated discovery has been proven. The adapter must obtain the approval digest and idempotency key from trusted tenant-scoped persistent records, never from the requester. SHA-256 alone is not an authorization credential. It must atomically consume a single-use approval and reserve a dispatch before invoking the provider. A remote provider must independently honor idempotency; unknown outcomes must be quarantined rather than replayed. Validate schema and destination policy, OAuth scopes, TLS and egress enforcement in isolated staging.

Keep external execution and gateway forwarding disabled. No production claim until real MCP integration, security tests and CI pass.

## Trusted approval/execution binding

The pure `bind_approved_mcp_dispatch` helper now requires matching tenant, run and approval IDs from a consumed approval and a reserved execution before building the exact MCP contract. Callers must fetch these records under trusted database credentials and ensure the dispatch reservation is atomically transitioned with cancellation/fencing checks. This helper does not lock rows, authenticate records, consume approvals or invoke MCP servers. The resulting data must never be accepted as a bearer authorization token.

## Offline discovered-tool policy

`mcp_discovery_policy.authorize_discovered_tool` requires the server ID to be trusted, the requested tool to be server-scoped allowlisted, and the discovered tool name to exist exactly once. Duplicate, malformed or excessive discovery records fail closed. **This does not authenticate the server**: an actual MCP client must validate transport identity, OAuth credentials, capability negotiation and tool schemas; obtain trusted policy from tenant-scoped configuration; and combine this gate with the existing consumed-approval and reserved-execution gate before any side effect.

## MCP 2026-07-28 stateless envelope

`mcp_protocol_envelope.build_mcp_tool_call` serializes an already-bound tool call into JSON-RPC `tools/call`, including the `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` routing headers and client metadata. It revalidates canonical argument integrity before constructing the request. This is **offline serialization only**, not an HTTP client or authentication layer. Real integration must follow the 2026-07-28 stateless specification, authenticate the destination and issuer, enforce TLS/egress policy and validate responses. Never pass user-created `bound_call` as trusted evidence.
