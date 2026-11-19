# Durable request lifecycle — offline prototype

`scripts/aepx_autonomous_request_state.py` stores planned, reserved, dispatched, uncertain, settled and failed states in a local SQLite WAL database. Transitions are transactional, require evidence, reject stale state changes and append an event audit. `recover_dispatched` marks ambiguous dispatched work uncertain rather than reissuing it. No network calls or automatic repairs are performed.

**Integration gate:** The budget reservation and request state databases are currently **separate**, and updates are not atomic across them. A real runner must combine them in one transaction or implement a rigorously tested transactional outbox before any billable API request. A request must never be dispatched without a durable reservation. Reconciliation requires independently authenticated provider usage. A three-attempt limit is represented in state transitions but is not yet a complete automated repair controller.

Next: verify CI, unify request/budget transaction boundaries, implement provider adapter and authenticated usage reconciliation, validate Docker sandbox, add supervised task execution and CI polling. No auto-merge, deployment, external MCP forwarding or chargeable OCI provisioning.
