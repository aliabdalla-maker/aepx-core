# Remote MCP delivery reconciliation — safety contract

This PR does **not** invoke remote tools. It records a durable `uncertain`
receipt before a remote attempt. A second reservation for the same tenant
and event is rejected, even if the first worker crashed. Operators must
independently check the provider's idempotency-key status and obtain
documented evidence before marking an outcome `confirmed` or `failed_safe`.

**Important:** `failed_safe` must mean the provider definitively confirms
that no business effect occurred. A timeout, 5xx or lost acknowledgement
is **not** proof of failure and must remain `uncertain`.

The caller must verify the worker/operator identity and approval independently.
The `authorized` flag is a library-level assertion, not authentication.
No retry is permitted solely on the basis of this local receipt. An actual
remote adapter must use the same stable idempotency key with a provider that
supports idempotency or require manual reconciliation.

## Release checklist
- Obtain green offline and PostgreSQL CI; queued workflows are not a pass.
- Validate non-owner RLS role and tenant-isolation constraints.
- Add disposable DB integration tests for concurrent duplicate reservations.
- Implement trusted provider status lookup and authenticated operator review.
- Test crash-before-call, timeout-after-effect, duplicate requests and
  inconsistent provider responses against a sandbox.
- Add structured audit, latency metrics, alert routing and bounded retries.
- Complete OCI staging restore and rollback drills before any deployment.

## Required evidence verifier

`reconcile_remote` now requires an injected `verify_evidence` callable returning exactly `True` after independently checking provider status, reviewer authorization, tenant, event, provider and idempotency key. `authorized=True` alone cannot mark an uncertain action confirmed or failed-safe. The caller must configure the verifier from trusted application code, not from an untrusted request. No production provider verifier is included; reconciliation remains disabled without one.
