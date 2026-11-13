"""Offline-only Docker sandbox command policy.

Builds argv, never invokes Docker. No provider credentials, network, mounts,
Docker socket or live HITL dispatch integration are permitted here.
"""
import re

class SandboxPolicyDenied(ValueError):
    pass

_DIGEST = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")

def offline_container_argv(*, image_digest, command, memory_mb=128, cpus=0.5,
                           pids_limit=32):
    """Return a fail-closed argv for an explicitly offline disposable workload."""
    if not isinstance(image_digest, str) or not _DIGEST.fullmatch(image_digest):
        raise SandboxPolicyDenied("immutable sha256 image digest required")
    if (not isinstance(command, (tuple, list)) or not command or
        any(not isinstance(x, str) or not x or "\x00" in x for x in command)):
        raise SandboxPolicyDenied("nonempty argument vector required")
    if (type(memory_mb) is not int or not 64 <= memory_mb <= 512 or
        type(pids_limit) is not int or not 8 <= pids_limit <= 64 or
        type(cpus) not in (int, float) or not 0 < cpus <= 1):
        raise SandboxPolicyDenied("sandbox bounds invalid")
    return [
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--security-opt=seccomp=builtin",
        "--pids-limit", str(pids_limit),
        "--memory", f"{memory_mb}m", "--memory-swap", f"{memory_mb}m",
        "--cpus", str(cpus), "--user", "65534:65534",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--init", "--stop-timeout", "1",
        image_digest, *command,
    ]
