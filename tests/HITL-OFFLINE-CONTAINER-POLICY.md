# Offline Docker sandbox profile (policy only)

`app.hitl_offline_container_policy.offline_container_argv` builds a
non-executing argument vector for an offline disposable workload. It does
**not** call Docker, launch containers, wire into HITL dispatch, or send
external provider requests. The caller must supply an already-present,
digest-pinned image and a trusted command.

The profile denies networking, removes Linux capabilities, explicitly requests Docker's built-in
seccomp profile (`--security-opt=seccomp=builtin`, subject to host verification), disallows privilege escalation, uses a read-only
root filesystem and a non-root UID, and applies CPU, memory and PID limits.
Docker documents these run options: https://docs.docker.com/reference/cli/docker/container/run/

## Remaining hard gates

- Add an independent container supervisor with enforced wall-clock timeout,
  container kill, cgroup process-tree cleanup and verified cleanup evidence.
- Never grant the workload Docker socket, host PID/network namespaces, host
  mounts, cloud credentials, or provider tokens.
- Verify actual seccomp/AppArmor and network restrictions on the target
  Docker host. This policy builder alone does not prove isolation.
- Add isolated crash injection and provider idempotency/reconciliation
  before any network-enabled or live dispatcher integration.
- Keep OCI staging on explicitly approved Always Free resources only.

No deployment, external execution or production configuration changes.
