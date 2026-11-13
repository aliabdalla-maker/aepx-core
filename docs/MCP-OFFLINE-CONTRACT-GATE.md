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

## 2026-07-28 metadata correction

The stateless request now mirrors `MCP-Protocol-Version` into `_meta.io.modelcontextprotocol/protocolVersion` and includes `_meta.io.modelcontextprotocol/clientCapabilities` (empty for this offline builder), plus `Content-Type: application/json`. Tests check header/body consistency and reject unsafe JSON-RPC IDs. The builder intentionally does not support schema-defined `x-mcp-header` parameter mirroring or MRTR and is not yet a conformant full transport client. Those features, authenticated transport, trusted server policy, real gateway enforcement and response validation remain release blockers.

## Offline response gate and Streamable HTTP Accept

The request builder now advertises both `application/json` and `text/event-stream` via `Accept`. `mcp_response_gate.validate_mcp_json_response` checks bounded JSON-RPC response bodies, duplicate keys, exact request-ID correlation, protocol errors and tool-level `isError`. It **does not** process SSE frames or implement an HTTP transport. Real transport must authenticate TLS/OAuth, handle SSE safely, validate response content schemas, manage deadlines, and quarantine uncertain side effects rather than retrying them.

## Bounded offline SSE parsing

`mcp_sse_gate.validate_mcp_sse_response` accepts only a complete, bounded, single-message SSE buffer and delegates JSON-RPC correlation to the existing response validator. It rejects ambiguous multi-response streams, resume IDs, retry instructions, unknown event types and malformed framing. It is **not** a streaming HTTP client, and intentionally rejects several legal SSE patterns (including CRLF and resumable streams); do not describe it as general SSE compliance. Authenticated Streamable HTTP, live incremental parser, deadline enforcement, credential isolation and provider outcome reconciliation remain pending.

## SSE framing and CI follow-up

The offline SSE gate now accepts standard CRLF event framing while rejecting lone carriage returns, incomplete event terminators and excessive line counts. It still deliberately handles only a bounded, complete-buffer, single-response subset: no authenticated HTTP transport, incremental stream reader, reconnect/resume support, OAuth or actual tool dispatch. MCP CI push filters now cover all offline MCP modules and tests, not only the original contract gate. Passing offline CI cannot substitute for end-to-end release gates G2–G6.
