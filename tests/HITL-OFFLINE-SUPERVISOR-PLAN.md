# Offline HITL container supervisor lifecycle — plan only

The pure function `offline_supervisor_plan` returns immutable Docker argv
for a disposable, digest-pinned, network-disabled container, plus kill,
inspect and forced-removal argv. It validates a 128-bit hexadecimal execution
identifier and a finite deadline up to 60 seconds. No command is executed.

**Critical:** The presence of a kill/cleanup argv does NOT prove timeout
enforcement or cleanup. Before enabling an actual supervisor:

1. Use a trusted host-side supervisor with an independently enforced monotonic
   deadline, unique name reservation, and daemon identity verification.
2. On timeout, kill the identified container and inspect the daemon state.
   Verify removal and process-tree/cgroup cleanup; fail closed on uncertainty.
3. Prevent any workload from controlling the Docker socket or host namespaces.
4. Run offline adversarial tests for child/grandchild escape, network access,
   filesystem writes, resource exhaustion and supervisor SIGKILL.
5. Prove durable receipt reconciliation and provider idempotency before
   network-enabled or live HITL integration.
6. Keep OCI staging isolated and on approved Always Free resources only.

The plan has no external execution, live dispatch, OCI provisioning, or
production deployment capability.

## Verified cleanup prerequisites

Do not use `docker run --rm` in the plan: automatic removal destroys the exited container's inspectable state. A trusted supervisor must inspect the exact daemon-issued container ID, verify its image and stopped state, remove it, and independently establish both Docker absence and absence of matching cgroup/process-tree members. The pure verification functions only check supplied evidence; they do not authenticate the Docker daemon or collect OS process evidence. Never report successful cleanup from a name-only check or a failed inspect command alone.
