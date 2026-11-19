# API usage accounting — offline policy module

The module `scripts/aepx_autonomous_usage_ledger.py` supports duplicate request rejection, decimal token-based cost calculation, immutable-style returned ledger values, receipt reconciliation and a pre-request budget reservation check.

**Not a trusted provider integration.** An external executor must obtain token counts from authenticated OpenAI API responses, use a reviewed and versioned model price table, account for cached/reasoning tokens and all billable usage, reserve worst-case request spend, persist receipts atomically, and reconcile actual provider billing. Requests with missing or ambiguous usage must be blocked pending reconciliation. This module alone cannot guarantee a hard financial cap, and it does not call an API.

Next: verify CI, add trusted provider adapter and durable atomic reservations, prevent parallel overspending, verify request IDs and retries, test crash recovery, and connect to a supervised runner with a container-isolated workspace. No auto-merge, deployment, OCI chargeable provisioning or external MCP forwarding.
