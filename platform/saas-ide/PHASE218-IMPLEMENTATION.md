# Phase 2.18 — MCP operations and provider contracts

Status: **HOLD — draft PR; no merge, deployment, or live execution**.

## Implemented
- Provider capability registry and explicit reviewed classification of MCP tools as read-only or side-effecting.
- Side-effecting tools require an opt-in `http-header-v1` idempotency contract, signed-receipt capability declaration, and receipt trust anchor. This configuration is a gate, **not proof** of provider behavior.
- Signed Ed25519 receipt verification from Phase 2.17, including synthetic tampering tests.
- OIDC membership-scoped owner/admin APIs for listing execution states, aggregate counts, signed receipt reconciliation, and stale quarantine.
- Hybrid IDE operations panel showing states and an explicit signed receipt reconciliation action.
- One-shot stale quarantine worker for external scheduling; no MCP calls, no automatic replay.
- PostgreSQL integration tests for role isolation and invalid operations, offline contract tests, and forward migration 008.

## Operational configuration
- `IDE_MCP_<SERVER>_READ_ONLY_TOOLS`: reviewed comma-separated tool list.
- `IDE_MCP_<SERVER>_SIDE_EFFECT_TOOLS`: reviewed comma-separated tool list.
- `IDE_MCP_<SERVER>_IDEMPOTENCY_CONTRACT=http-header-v1`: only for providers with documented deduplication support.
- `IDE_MCP_<SERVER>_SIGNED_RECEIPTS=true`: only after verifying provider receipt format.
- `IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY`: out-of-band trusted Ed25519 public key, base64.
- `IDE_MCP_RECOVERY_ENABLED=true`, `IDE_MCP_RECOVERY_TENANTS`, `IDE_MCP_RECOVERY_AGE_SECONDS`: required for explicitly scheduled one-shot quarantine.

Apply migration `008_phase218.sql` using the migration role to existing databases. New CI databases apply 001–008.

## Unverified and outstanding
1. Final SHA dedicated and full repository CI must pass.
2. Actual provider-side deduplication and signed receipt issuance have not been verified; no real provider contract is configured.
3. Scheduler deployment and end-to-end dashboard browser acceptance remain unverified.
4. Independent security sign-off and explicit release authorization are missing.
5. Read-only tool classifications require human review; unclassified tools fail closed.
6. Recovery is quarantine only; do not automatically replay unknown outcomes.

**Never enable production gateway forwarding or live external execution as part of this phase.**
