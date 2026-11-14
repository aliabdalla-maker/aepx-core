# Provider first-dispatch admission (offline only)

`scripts/aepx_provider_dispatch_admission.py` defines a pure, fail-closed admission policy. It requires a **new** `reserved` status, verified approval, committed budget, isolated worker, positive integer fencing token, bounded tenant/request identifiers and a provider idempotency key. Any replay status (`already_reserved`, `already_settled`) is denied.

**This does not authorize production execution.** Inputs are caller-supplied and **not authenticated** by this module. The returned `eligible_for_fenced_dispatch` decision is only a local precondition; it is not a dispatch permit or proof of an exclusive lease. Before integrating a provider, implement trusted identity/approval verification, atomic PostgreSQL reservation+dispatch claim, fencing checks at the external gateway, durable provider request IDs, crash recovery and billing reconciliation. Keep provider execution disabled until those checks pass real concurrent and crash-injection tests.

No network, LLM, shell, provider or cloud operations are performed by this module.
