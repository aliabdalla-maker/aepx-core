# Budget reconciliation acceptance gate

Ambiguous API outcomes retain the original reservation. `reconcile_uncertain(conn, request_id, charge_usd, receipt_id=..., verified=True)` records an immutable-identifier reconciliation and settles the hold in one SQLite transaction. The `verified=True` flag is **only a caller assertion**: it is not cryptographic proof. An independently trusted provider billing adapter and human-authorized reconciliation policy must verify receipt identity and actual charges before calling this method.

The module rejects repeated receipt identifiers, repeated settlement, amounts above the reservation and integer overflow. It does not support releasing holds without a verified provider outcome. No automatic network calls, deployments, merges or external MCP execution are performed.

Next: verify CI, implement trusted OpenAI usage/price adapter, introduce durable atomic request reservations before API calls, test process crash injection and container cleanup, then run a supervised pilot.
