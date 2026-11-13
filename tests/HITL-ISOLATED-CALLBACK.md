# Isolated HITL callback prototype

The opt-in `app.hitl_isolated_callback.run_isolated_callback` runner uses a
spawned Python child process, a bounded one-way pipe for result IPC, and an explicit entrypoint allowlist. The parent reads the IPC result before joining the child to avoid multiprocessing Queue feeder-thread deadlocks. Abrupt child death and timeout remain uncertain outcomes. Offline
tests are in `tests/test_hitl_isolated_callback.py`.

This module is **not connected to dispatch_batch** and does not enable remote
execution. A timeout or child crash is an **uncertain remote outcome**, not
proof that an external action did not occur. Do not blindly replay it.

## Production blockers

- Terminating a Python child does not guarantee termination of grandchildren
  or already-issued provider requests. Use an OS/container supervisor with
  cgroup/process-tree termination, resource limits and restricted egress.
- Reserve and commit a remote receipt before the provider request, then use
  provider idempotency and independently verified reconciliation.
- Require a signed, trusted adapter registry rather than caller-supplied
  import paths. Authenticate tenant, worker and approved action identity.
- Test crash at reservation, dispatch, provider acknowledgment and settlement.
- Verify timeout handling, duplicate billing prevention, audit integrity and
  fail-closed network policy in disposable staging before wiring the runner
  into live dispatch.

No OCI resources, external providers or production workloads are touched.

## Child exception regression

The child exception path must use `Connection.send`, not `Queue.put`, and must close its pipe endpoint. The offline failure test asserts the precise `callback failed: outcome uncertain` result so a broken IPC exception handler cannot silently degrade into a timeout. This remains an opt-in local prototype, not a production sandbox.

## Early child-exit detection

The parent waits on both the result pipe and child process sentinel, using one deadline that begins before process startup. An abruptly exited child must fail closed promptly instead of waiting the full adapter timeout. This does not provide cgroup process-tree termination or guarantee that an external provider request was cancelled.

## IPC result validation

The parent requires an exact two-item tuple containing an approved status and a Boolean-or-None result. Invalid adapter return types are rejected by the child; malformed IPC messages are rejected by the parent. A result remains untrusted until the child exits successfully. This does not replace a sandbox or provider-side idempotency.
