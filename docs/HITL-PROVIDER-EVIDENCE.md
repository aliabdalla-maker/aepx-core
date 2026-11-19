# Trusted MCP/provider reconciliation evidence

Use `provider_evidence_verifier(trusted_provider=..., read_provider_status=...)`
as the `verify_evidence` callback in `reconcile_remote`. The status reader
must obtain authoritative status independently, from an authenticated provider
API or verified signed receipt store. It must never return request-body fields
as if they were independently verified.

For each query the reader receives tenant ID, event ID, provider and
idempotency key. Return exact identifiers, terminal state, opaque evidence
reference and literal `verified: True` **only after validating authenticity**.

Fail closed on missing status, timeouts, mismatches, invalid signatures or
uncertain outcomes. A `failed_safe` outcome is permitted only when an
authoritative provider response establishes that state, not merely when a
request timed out.

This PR adds a verification adapter and offline tests. It does NOT add a
production provider connector, credential management, webhook signature
validation, network calls, or permission to execute external effects.

Next: implement a real provider-specific status reader, bounded HTTPS
timeouts, credential rotation, replay prevention, audit logs, isolated
network egress and end-to-end PostgreSQL acceptance. Keep all external
execution disabled until these controls are independently validated.
