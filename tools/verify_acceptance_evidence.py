#!/usr/bin/env python3
"""Offline, fail-closed AEP-X acceptance evidence verifier.

Input JSON:
{"milestones":[{"id":"postgres-rls","weight":30,"evidence":[
 {"path":"evidence/rls.json","sha256":"<64 lowercase hex>","result":"pass"}]}]}
Run from a trusted checkout: python tools/verify_acceptance_evidence.py manifest.json
Only locally supplied immutable digests are checked. This does NOT authenticate
test runners or prove that tests actually ran; independent provenance is required.
"""
import hashlib
import os
import stat
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


MAX_EVIDENCE_BYTES = 16 * 1024 * 1024


def safe_digest(root: Path, relative: str):
    """Hash beneath root using no-follow descriptors, or fail closed.

    Requires POSIX dir_fd/O_NOFOLLOW; never falls back to check-then-open.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("secure evidence hashing requires POSIX no-follow support")
    if "\\x00" in relative or "\\\\" in relative or relative.startswith("/"):
        raise ValueError("invalid evidence path syntax")
    parts = relative.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("invalid evidence path components")
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags_file = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    opened = []
    try:
        fd = os.open(root, flags_dir)
        opened.append(fd)
        for part in parts[:-1]:
            fd = os.open(part, flags_dir, dir_fd=fd)
            opened.append(fd)
        leaf = os.open(parts[-1], flags_file, dir_fd=fd)
        opened.append(leaf)
        before = os.fstat(leaf)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("evidence is not a bounded regular file")
        state = hashlib.sha256()
        count = 0
        while True:
            chunk = os.read(leaf, min(1024 * 1024, MAX_EVIDENCE_BYTES + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_EVIDENCE_BYTES:
                raise ValueError("evidence exceeds 16 MiB")
            state.update(chunk)
        after = os.fstat(leaf)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ) or count != after.st_size:
            raise ValueError("evidence changed during hashing")
        return state.hexdigest()
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key rejected")
        result[key] = value
    return result


def verify(manifest_path: Path):
    root = manifest_path.resolve().parent
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("manifest exceeds 1 MiB")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON number rejected")))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    milestones = manifest["milestones"]
    if not isinstance(milestones, list) or not milestones or len(milestones) > 100:
        raise ValueError("milestones must be a nonempty list")
    ids = set()
    total_weight = 0
    verified_weight = 0
    results = []
    for milestone in milestones:
        if not isinstance(milestone, dict):
            raise ValueError("milestone must be an object")
        identifier = milestone["id"]
        weight = milestone["weight"]
        if not isinstance(identifier, str) or not IDENT.fullmatch(identifier) or identifier in ids:
            raise ValueError("invalid or duplicate milestone id")
        if type(weight) is not int or weight <= 0:
            raise ValueError("weights must be positive integers")
        ids.add(identifier)
        total_weight += weight
        evidence = milestone.get("evidence", [])
        passed = isinstance(evidence, list) and len(evidence) > 0
        if not isinstance(evidence, list) or len(evidence) > 100:
            raise ValueError("evidence must be a list of at most 100 entries")
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("evidence entry must be an object")
            relative = item.get("path")
            digest = item.get("sha256")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                raise ValueError("evidence path must be relative")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                passed = False
                continue
            try:
                actual = safe_digest(root, relative)
            except (OSError, ValueError):
                passed = False
                continue
            if actual != digest or item.get("result") != "pass":
                passed = False
        if passed:
            verified_weight += weight
        results.append({"id": identifier, "evidence_integrity_passed": passed})
    if total_weight != 100:
        raise ValueError("milestone weights must sum to 100")
    return {
        "evidence_integrity_percent": verified_weight,
        "independently_verified_percent": 0,
        "independent_verification_available": False,
        "warning": "Digest matching is not independent test attestation",
        "milestones": results,
    }


def main():
    if len(sys.argv) != 2:
        print("usage: verify_acceptance_evidence.py manifest.json", file=sys.stderr)
        return 2
    try:
        output = verify(Path(sys.argv[1]))
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if output["evidence_integrity_percent"] == 100 else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"acceptance evidence rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
