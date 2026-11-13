# Governed tool delivery: staging gate

This PR adds a **policy wrapper only**, not a live MCP adapter or a durable deduplication implementation. It requires:
- `HITL_DISPATCH_ENABLED=yes` plus trusted `enabled=True` at the dispatcher.
- `HITL_EXTERNAL_EFFECTS_ENABLED=yes` at the guarded adapter (independent kill switch).
- Explicit trusted tenant UUID and SHA-256 action-hash allowlists.
- Valid event UUID, approval UUID, actor, and `hitl.approval.consumed` topic.

**Do not enable external effects yet.** Event fields are untrusted; an actual MCP adapter must independently verify the approval against a restricted database and enforce per-tool authorization. Stable event-ID deduplication must occur at the side-effect boundary, ideally in the same transaction as the business action. An independent remote API without idempotency cannot be made exactly-once by a local ledger.

## Next required work
1. Obtain green CI on PR #53 merge and PR #54 acceptance; resolve queued runners.
2. Review/merge PR #54 only after the audit migration and restricted grants pass.
3. Implement a DB-backed execution receipt ledger and transactionally idempotent **local** action handler; prove concurrent duplicates cannot double-apply.
4. For remote MCP calls, require provider idempotency keys or explicit reconciliation before replay.
5. Add authenticated worker/operator identities, rate and cost limits, structured audit events and observability.
6. Exercise isolated OCI staging and recovery rehearsal before production review.
