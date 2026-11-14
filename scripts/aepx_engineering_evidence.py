"""Offline evidence artifact verification for engineering iteration reviews.

No network, subprocess, model calls, approvals or code execution.
"""
import hashlib
import os
import re
import stat
from pathlib import Path

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

class EvidenceDenied(ValueError):
    pass

def digest_artifact(root, relative_path):
    """Hash a regular artifact via descriptor-relative no-follow traversal.

    POSIX-only; rejects platforms without O_NOFOLLOW/O_DIRECTORY. An attacker
    able to mutate file *contents* concurrently is outside this primitive's
    trust boundary; immutable artifact storage remains required.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise EvidenceDenied("secure descriptor traversal unavailable")
    root = Path(root)
    relative = Path(relative_path)
    if not root.is_absolute() or relative.is_absolute() or not relative.parts:
        raise EvidenceDenied("invalid artifact path")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise EvidenceDenied("invalid artifact component")
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in relative.parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
                raise EvidenceDenied("not a bounded regular artifact")
            digest = hashlib.sha256()
            read_total = 0
            while True:
                chunk = os.read(file_fd, min(65536, MAX_ARTIFACT_BYTES + 1 - read_total))
                if not chunk:
                    break
                read_total += len(chunk)
                if read_total > MAX_ARTIFACT_BYTES:
                    raise EvidenceDenied("artifact too large")
                digest.update(chunk)
            return "sha256:" + digest.hexdigest()
        finally:
            os.close(file_fd)
    except (OSError, ValueError) as exc:
        raise EvidenceDenied("artifact inaccessible or unsafe") from exc
    finally:
        if fd is not None:
            os.close(fd)

def verify_iteration_artifacts(state, number, root, manifest):
    """Verify every stage digest against supplied artifact paths.

    This proves bytes match manifest digests at read time only. It does not
    authenticate authors, approvals, test execution or provenance.
    """
    from scripts.aepx_engineering_iteration_state import validate, STAGES
    validate(state)
    if type(number) is not int or number < 1 or number > len(state["iterations"]):
        raise EvidenceDenied("unknown iteration")
    item = state["iterations"][number - 1]
    if item["stage"] != "completed" or not isinstance(manifest, dict) or set(manifest) != set(STAGES):
        raise EvidenceDenied("incomplete iteration or manifest")
    for stage in STAGES:
        expected = item["evidence"][stage]
        if not DIGEST.fullmatch(expected):
            raise EvidenceDenied("unverified evidence reference")
        path = manifest[stage]
        if not isinstance(path, str) or digest_artifact(root, path) != expected:
            raise EvidenceDenied("artifact digest mismatch")
    return True
