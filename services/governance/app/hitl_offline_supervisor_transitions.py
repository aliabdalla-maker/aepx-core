"""Pure fail-closed lifecycle state machine for offline HITL containers.

No Docker calls, no dispatcher integration, no external execution.
A trusted supervisor must authenticate daemon observations and enforce deadlines.
"""
import math
from .hitl_offline_container_policy import SandboxPolicyDenied
from .hitl_offline_cleanup_verification import (
    verified_container_commands, verify_offline_cleanup_absent,
)

def offline_supervisor_transition(*, phase, snapshot=None, expected_name=None,
                                  expected_image_id=None, elapsed_seconds=None,
                                  timeout_seconds=None, expected_container_id=None,
                                  inspect_not_found=None,
                                  matching_processes_absent=None):
    """Choose the next allowed action from independently verified evidence.

    Actions are descriptive; this function NEVER invokes Docker. The caller
    must bind observations to the same daemon and immutable container ID.
    """
    if phase == "created":
        if snapshot is None or not expected_name or not expected_image_id:
            raise SandboxPolicyDenied("authenticated creation evidence required")
        commands = verified_container_commands(
            snapshot, expected_name=expected_name,
            expected_image_id=expected_image_id,
        )
        if expected_container_id is not None and commands["container_id"] != expected_container_id:
            raise SandboxPolicyDenied("created container ID mismatch")
        if snapshot["State"]["Running"]:
            raise SandboxPolicyDenied("newly created container unexpectedly running")
        return {"phase": "verified", "action": "start_by_id",
                "container_id": commands["container_id"]}
    if phase == "running":
        if (type(elapsed_seconds) not in (int, float) or
            not math.isfinite(elapsed_seconds) or elapsed_seconds < 0 or
            type(timeout_seconds) not in (int, float) or
            not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60):
            raise SandboxPolicyDenied("trusted monotonic deadline evidence required")
        if snapshot is None or not expected_name or not expected_image_id:
            raise SandboxPolicyDenied("authenticated running evidence required")
        commands = verified_container_commands(
            snapshot, expected_name=expected_name,
            expected_image_id=expected_image_id,
        )
        if (not isinstance(expected_container_id, str) or
            len(expected_container_id) != 64 or
            commands["container_id"] != expected_container_id):
            raise SandboxPolicyDenied("running container ID not fenced")
        if not snapshot["State"]["Running"]:
            return {"phase": "stopped", "action": "inspect_exit_by_id",
                    "container_id": commands["container_id"]}
        if elapsed_seconds >= timeout_seconds:
            return {"phase": "timed_out", "action": "kill_by_id",
                    "container_id": commands["container_id"],
                    "argv": commands["kill_argv"]}
        return {"phase": "running", "action": "poll_by_id",
                "container_id": commands["container_id"]}
    if phase == "removed":
        verify_offline_cleanup_absent(
            inspect_not_found,
            matching_processes_absent=matching_processes_absent,
        )
        return {"phase": "clean", "action": "complete"}
    raise SandboxPolicyDenied("unknown or unverified lifecycle transition")
