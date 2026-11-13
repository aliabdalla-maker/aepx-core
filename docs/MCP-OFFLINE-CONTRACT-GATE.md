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

## Composed offline preflight

`mcp_preflight.prepare_mcp_preflight` composes the server/tool discovery allowlist, exact consumed approval and reserved execution evidence, canonical argument digest, and protocol request envelope into a single pure preflight operation. Its `trusted_*` inputs must originate from independently authenticated, tenant-scoped database/configuration queries. **It does not fetch trusted records, lock rows, transition execution state, authenticate a server or invoke a tool.** A real dispatcher must atomically claim the reserved execution after revalidating cancellation and membership, then use a sandboxed authenticated transport. No claims of exactly-once external effects are made. Remaining release gates G2–G6 are not satisfied.

## PostgreSQL schema alignment and read-only preflight

The persisted `ide_tool_approvals` digest column is `args_sha256`, not `arguments_sha256`. The offline binding and fixtures now use the actual schema. `mcp_db_preflight.prepare_mcp_db_preflight` loads tenant-scoped approval and reserved execution evidence and validates the canonical request, then rolls back to clear `SET LOCAL` scope. It does not claim dispatch or execute tools. **A race remains between this read-only preflight and the existing separate `begin_dispatch` transaction**; production wiring must repeat the exact contract checks under the same row lock/transaction that transitions the execution to `dispatching`. Fake DB tests are not PostgreSQL RLS integration evidence. Do not enable external dispatch.

## Atomic contract-bound dispatch claim

`mcp_atomic_claim.claim_approved_mcp_call` locks the active run, consumed approval and reserved execution, checks live requester/approver membership, exact server/tool and canonical argument digest, then transitions the execution to `dispatching` before committing. The caller must provide a trusted tenant identity and independently verified tool allowlist. This function **does not call the external MCP provider**; it is not wired to the governed worker. Its SQL-interaction tests use a fake database and do not establish real PostgreSQL concurrency, RLS, cancellation race or deadlock behavior. After a committed claim, failed transport or worker crash must be recorded as `outcome_unknown`, never automatically replayed. Do not enable external dispatch before end-to-end tests and authenticated transport.

## PostgreSQL atomic-claim integration regression

The real-PostgreSQL integration suite now includes a competing two-session `claim_approved_mcp_call` race, tampered argument denial, cross-tenant denial, single-use replay rejection and execution-ledger RLS checks. It requires the configured PostgreSQL integration environment and remains **unverified until CI actually executes it**. This tests the DB claim only; authenticated MCP transport, worker integration and provider side effects are deliberately absent. A separate cancellation-vs-claim stress test and independent security review remain release blockers.

## Cancellation-before-claim PostgreSQL acceptance

The PostgreSQL integration suite now asserts that a previously approved, consumed and reserved MCP execution cannot be claimed after its run is cancelled through the API. This checks the fail-closed cancelled-run path, but is **not** a simultaneous cancellation-versus-claim stress test. True concurrent cancellation/claim interleavings, worker crash outcomes, external-provider idempotency and verified egress isolation remain mandatory before live execution.

## HTTP response media and status gate

`mcp_http_response_gate.validate_mcp_http_response` rejects non-200 statuses, missing/unsupported media types, oversized bodies, malformed JSON and uncorrelated SSE or JSON responses. It selects the existing bounded offline JSON or SSE validator. This matches the 2026-07-28 Streamable HTTP request-response media types but **does not** implement HTTP connections, OAuth/TLS, SSE incremental notifications, subscriptions, request cancellation, redirects or egress isolation. In 2026-07-28, legacy GET streams, protocol-level sessions and Last-Event-ID resume are removed; do not implement those as required current-version features. Keep external execution disabled.

## Exact HTTPS endpoint policy (offline)

`mcp_endpoint_policy.validate_mcp_endpoint` rejects unapproved URLs, HTTP, credentials in URLs, fragments, queries, encoded paths, noncanonical DNS names, IP literals and non-443 ports. It does not perform DNS resolution, TLS, OAuth or HTTP requests. The network worker **must** enforce DNS/IP pinning and private/metadata address blocking at connection time, disable redirects, validate certificate identity, restrict OAuth token audience, and route through the independently verified egress gateway. URL validation alone is not SSRF protection; keep external execution disabled.

## DNS answer policy (offline)

`mcp_dns_policy.validate_mcp_dns_answers` rejects empty, oversized, duplicate, malformed, private, loopback, link-local, metadata and mixed public/private address sets, including IPv4-mapped IPv6. The function does **not** resolve DNS or enforce where a socket connects. The gateway must independently resolve, pin, and revalidate the actual destination at connect time, deny redirects and bypass routes, and verify TLS hostname/certificate. DNS rebinding remains a production blocker until tested at the enforced gateway. No live MCP execution is enabled.

## Offline transport policy composition

`mcp_transport_policy` combines exact approved HTTPS endpoint, DNS answer and server identity checks before selecting the bounded correlated HTTP JSON/SSE response gate. Its inputs are **not independently authenticated**; callers must never use the returned policy as proof of safe network execution. No HTTP requests, TLS, OAuth, DNS lookup, sockets or MCP dispatch occur. Actual gateway destination pinning, token audience, worker integration and concurrent cancellation remain release blockers.

## Transport module syntax repair and peer regression

A merged version of `mcp_transport_policy.py` contained literal escaped newline tokens that prevented Python compilation. The repair restores valid source formatting and adds offline tests for approved versus substituted connected peers. Peer identity is still supplied by a caller and therefore **does not establish socket-level enforcement**. The actual gateway must obtain peer identity from its connected socket and enforce TLS, DNS/IP pinning and egress controls.

## MCP 2026-07-28 outbound POST contract (offline)

`mcp_post_request_gate.validate_mcp_post_request` checks exact allowlisted HTTPS endpoint, POST method, JSON content type, both JSON and SSE Accept media types, bounded correlated JSON-RPC request and rejects legacy session/resume headers, duplicate JSON keys and malformed values. It does **not** build or send HTTP requests, handle OAuth resource indicators or independently authenticate any request metadata. A production gateway must enforce token audience, TLS and socket-level destination policy; keep execution disabled.

## Negotiated protocol version pinning

The outbound POST gate can now require `MCP-Protocol-Version` to exactly match a trusted, already-negotiated protocol version, rejecting missing, duplicate and downgraded values. The gate does not itself negotiate or authenticate a version. Note: protocol features differ by version; the 2025-11-25 Streamable HTTP specification supports GET, session IDs and resume. The offline request gate deliberately rejects session/resume headers and supports only a restricted POST subset, so it is **not a general conformant client for all negotiated versions**. Do not enable live transport until version-specific interoperability tests pass.

## Offline protocol version policy

`mcp_version_policy.select_mcp_protocol_version` accepts only an explicitly trusted server version present in both the client and supported-version allowlists, and returns a deliberately restricted POST-only profile. Current local policy defaults to 2025-11-25 as a version label, **not** proof of complete compatibility with all 2025-11-25 features. A future authenticated initialization exchange must supply server evidence; GET/session/resume support and capability negotiation need separate implementations and conformance tests. Never silently downgrade.

## Initialize response gate (offline)

`mcp_initialize_gate.validate_mcp_initialize_response` parses a bounded JSON-RPC initialization result, requires request ID correlation, server name, capabilities and trusted version policy, and rejects malformed or downgraded responses. It does **not** authenticate server identity or establish a session; the response bytes must originate from a verified TLS/OAuth connection. Client initialization request, `notifications/initialized`, capability compatibility, live POST/SSE transport and end-to-end conformance remain pending.

## CI trigger correction and approved server-name binding

The PR workflow now watches POST, version-policy and initialize-gate files (previously these were only in the push path filter), so changing these files should schedule the offline contract job. The initialization gate optionally requires the returned `serverInfo.name` to match a trusted approved name. This is a consistency check on supplied bytes, **not** authentication: the future gateway must bind TLS identity and token audience to the approved MCP resource.

## Initialized notification contract

`mcp_initialized_gate.validate_mcp_initialized_notification` validates the bounded JSON-RPC `notifications/initialized` message, rejects request IDs and unexpected payloads, and binds the supplied version to a trusted expected value. It does not transmit the notification, authenticate the initialization result or establish a live MCP session. CI compiles and tests the gate; the authenticated initialize/initialized handshake and interoperability remain pending.
