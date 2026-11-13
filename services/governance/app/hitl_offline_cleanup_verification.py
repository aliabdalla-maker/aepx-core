"""Pure validation of Docker inspect snapshots for an offline workload.

Never invokes Docker. A trusted supervisor must obtain authenticated
snapshots from the daemon and verify container identity independently.
"""
from .hitl_offline_container_policy import SandboxPolicyDenied

def verify_offline_container_snapshot(snapshot, *, expected_name, expected_image_id=None):
    if (not isinstance(snapshot, dict) or
        snapshot.get("Name") != "/" + expected_name or
        not isinstance(snapshot.get("Id"), str) or len(snapshot["Id"]) != 64 or
        any(ch not in "0123456789abcdef" for ch in snapshot["Id"])):
        raise SandboxPolicyDenied("container identity not verified")
    if expected_image_id is not None and snapshot.get("Image") != expected_image_id:
        raise SandboxPolicyDenied("container image identity mismatch")
    state = snapshot.get("State")
    if not isinstance(state, dict) or type(state.get("Running")) is not bool:
        raise SandboxPolicyDenied("container state not verified")
    return {"container_id": snapshot["Id"], "running": state["Running"]}

def verify_offline_cleanup_absent(inspect_not_found, *, matching_processes_absent):
    """Only accept independent daemon absence and process-tree cleanup evidence."""
    if inspect_not_found is not True or matching_processes_absent is not True:
        raise SandboxPolicyDenied("container cleanup not verified")
    return True

def verified_container_commands(snapshot, *, expected_name, expected_image_id):
    """Return destructive argv only after identity and image validation.

    Callers MUST independently authenticate the Docker daemon and prevent
    time-of-check/time-of-use replacement of the verified container ID.
    """
    evidence = verify_offline_container_snapshot(
        snapshot, expected_name=expected_name, expected_image_id=expected_image_id
    )
    cid = evidence["container_id"]
    return {
        "container_id": cid,
        "kill_argv": ("docker", "kill", cid),
        "inspect_argv": ("docker", "inspect", "--type=container", cid),
        "cleanup_argv": ("docker", "rm", "--force", cid),
    }
