# Durable budget reservations — single-host prototype

The SQLite reservation module implements `BEGIN IMMEDIATE` transactions, unique request IDs, atomic settlement, held balances, non-escalating budget caps, and durable **uncertain** reservations. It does not make OpenAI API calls or trigger development actions.

Use `connect(path)`, `initialize(conn, cap_usd)`, `reserve(conn, request_id, worst_case_usd)` **before** an API call, and `settle(conn, request_id, verified_charge_usd)` only after receiving a trusted, reconciled usage receipt. If the response is ambiguous, use `mark_uncertain` to retain the reservation; never automatically release it. `snapshot(conn)` reports available funds.

**Important limitations:** Single-host local SQLite only. No distributed locking, API authentication, model pricing integration, provider billing reconciliation, signed receipts, or secure worker execution. Cost can exceed reserved funds if the provider bills above the declared worst case; the module deliberately rejects such settlement and requires manual reconciliation. Never store the database on a shared network filesystem. A production runner must keep API secrets outside the test container and verify actual spend with provider records.

Next: CI validation, trusted API adapter, worst-case token/cost calculation, durable request state machine and idempotency, distributed concurrency design, and supervised end-to-end pilot. No auto-merge, deployment, external MCP execution or chargeable OCI resources.
