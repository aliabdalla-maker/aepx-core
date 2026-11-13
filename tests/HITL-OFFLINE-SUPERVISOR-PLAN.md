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

## Destructive command identity binding

The initial plan deliberately leaves kill and cleanup argv unset. Once a trusted supervisor has authenticated the daemon and inspected the named container, `verified_container_commands` validates its name, full 64-hex-character container ID and expected image ID and returns ID-bound kill/inspect/remove argv. Never kill or remove by name. The caller must guard against stale evidence, daemon substitution and time-of-check/time-of-use races. This is still pure planning code, not a running supervisor.

## Inspect evidence hardening

Before constructing any ID-bound destructive command, the offline validator now requires an explicit sha256 image ID and `HostConfig.NetworkMode=none`, `HostConfig.Privileged=false`, and `HostConfig.ReadonlyRootfs=true`. Docker inspect returns daemon-reported fields; a trusted executing supervisor must still authenticate the daemon, verify cgroup process cleanup, enforce deadlines, and check all remaining isolation options. This is not a runtime isolation certification.

## Expanded fail-closed inspect validation

The pure snapshot validator additionally requires capability drop ALL, no-new-privileges, explicit built-in seccomp, PID limit 8–64, memory 64–512 MiB and memory-swap equal to memory. Host Docker inspect normalization can differ by engine version; verify on the intended Docker host before integrating. This is only validation of supplied evidence and cannot certify kernel enforcement. Actual execution and cleanup remain disabled.
