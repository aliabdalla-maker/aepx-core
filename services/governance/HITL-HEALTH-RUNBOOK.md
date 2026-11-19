# HITL operational health — release and response runbook

Read-only `outbox_health` reports per-tenant counts for pending, leased,
delivered and dead events, oldest pending age, and alert names. It does not
expose payloads or execute network actions. Configure thresholds per
tenant and expected throughput; defaults are provisional, not production SLOs.

## Alert response
- `pending_backlog`: check worker availability, dispatcher disabled state,
  PostgreSQL health and downstream rate limits. Do not blindly raise retries.
- `dead_letters`: inspect redacted failure metadata and audit records.
  Replay only through the operator-authorised recovery procedure after
  independent downstream idempotency verification.
- `oldest_pending_age`: investigate stuck workers and lease expiry; do not
  run concurrent recovery scripts without a change record.

## Deployment gates
1. GitHub Actions runners must execute and pass offline and disposable
   PostgreSQL acceptance; queued does not mean green.
2. Verify non-owner, non-BYPASSRLS role and tenant isolation.
3. Review the separate tool-policy PR before any external adapter is wired.
4. Use a monitoring service with authenticated read-only access and
   cardinality controls; do not publish tenant identifiers as public labels.
5. Verify backup/restore, incident escalation and rollback in OCI staging.
6. Keep `HITL_DISPATCH_ENABLED` and `HITL_EXTERNAL_EFFECTS_ENABLED` disabled
   until explicitly approved by an operator and security reviewer.

No production credentials, endpoints, scheduler or live adapter are included.
