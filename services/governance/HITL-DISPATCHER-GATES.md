# HITL dispatcher release gate

`app.hitl_dispatcher.dispatch_batch` is a library function, **not a deployed worker**.
By default it returns dry-run status without claiming events. Enabling it
requires both `enabled=True` in trusted code and `HITL_DISPATCH_ENABLED=yes`,
plus an explicitly injected delivery adapter.

The adapter must be allowlisted and idempotent by the stable outbox event ID.
The dispatcher only permits topic `hitl.approval.consumed`, uses tenant-scoped
PostgreSQL lease primitives and fences settlement with worker ID and attempt
number. It stores only a redacted failure reason. A settlement failure is
raised, not hidden. A lease expiry after an external side effect can cause
redelivery; downstream deduplication is mandatory.

**Do not enable on production or connect live MCP tools.** Remaining gates:

1. Run `PYTHONPATH=services/governance python -m unittest discover -s tests -p 'test_hitl_dispatcher.py' -v`.
2. Verify the outbox lease/status migration is applied and includes `leased` and `dead` states, lease timestamps, owner, retry time and last error.
3. Reconcile PR #46 exhaustion recovery and add an operator-only dead-letter replay procedure.
4. Test multi-worker claim exclusivity, lease expiry, crash-after-delivery, stale settlement and retry exhaustion against disposable PostgreSQL.
5. Use non-owner, non-BYPASSRLS roles and scoped worker identity; do not derive tenant identity from untrusted payload.
6. Add adapter allowlist, per-tool policy, per-tenant budgets, explicit approval linkage, dry-run smoke, telemetry and kill switch.
7. Confirm CI and security review, then test isolated OCI staging and encrypted backup restoration.

No network adapter, scheduler, automatic service start, OCI deployment or production change is included in this PR.
