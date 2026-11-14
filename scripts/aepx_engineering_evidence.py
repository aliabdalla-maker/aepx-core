"""Offline evidence artifact verification for engineering iteration reviews.

No network, subprocess, model calls, approvals or code execution.
"""
import hashlib
import re
from pathlib import Path

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

class EvidenceDenied(ValueError):
    pass

def digest_artifact(root, relative_path):
    """Return a content digest for a regular artifact under a trusted directory."""
    root = Path(root)
    relative = Path(relative_path)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise EvidenceDenied("invalid evidence root")
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise EvidenceDenied("invalid artifact path")
    candidate = root / relative
    # Deny symlinks in every path component, not just the leaf.
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceDenied("symlinked evidence path")
    if not candidate.is_file() or candidate.stat().st_size > MAX_ARTIFACT_BYTES:
        raise EvidenceDenied("missing or oversized artifact")
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
            if stream.tell() > MAX_ARTIFACT_BYTES:
                raise EvidenceDenied("artifact too large")
    return "sha256:" + digest.hexdigest()

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
