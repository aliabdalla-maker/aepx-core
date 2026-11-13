"""Non-executing supervisor lifecycle plan for offline HITL sandbox.

This module produces Docker command argv only. A future independent,
privileged supervisor must implement timeouts, execute commands, verify
daemon ownership and cleanup. Never call it from live HITL dispatch.
"""
import re

from .hitl_offline_container_policy import offline_container_argv, SandboxPolicyDenied

_ID = re.compile(r"^[0-9a-f]{32}$")

def offline_supervisor_plan(*, execution_id, image_digest, command,
                            timeout_seconds=10, memory_mb=128,
                            cpus=0.5, pids_limit=32):
    if not isinstance(execution_id, str) or not _ID.fullmatch(execution_id):
        raise SandboxPolicyDenied("128-bit hexadecimal execution id required")
    if (type(timeout_seconds) not in (int, float) or
        not 0 < timeout_seconds <= 60):
        raise SandboxPolicyDenied("bounded supervisor deadline required")
    name = "aepx-offline-" + execution_id
    run = offline_container_argv(
        image_digest=image_digest, command=command, memory_mb=memory_mb,
        cpus=cpus, pids_limit=pids_limit,
    )
    # The name identifies the exact disposable workload. A real supervisor
    # must confirm daemon identity and reject pre-existing name collisions.
    run[2:2] = ["--name", name]
    return {
        "name": name,
        "run_argv": tuple(run),
        "kill_argv": ("docker", "kill", name),
        "inspect_argv": ("docker", "inspect", "--type=container", name),
        "cleanup_argv": ("docker", "rm", "--force", name),
        "timeout_seconds": timeout_seconds,
        "requires_cleanup_verification": True,
    }
