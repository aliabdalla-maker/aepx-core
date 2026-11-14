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
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def verify(manifest_path: Path):
    root = manifest_path.resolve().parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    milestones = manifest["milestones"]
    if not isinstance(milestones, list) or not milestones:
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
        if not isinstance(evidence, list):
            raise ValueError("evidence must be a list")
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("evidence entry must be an object")
            relative = item.get("path")
            digest = item.get("sha256")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                raise ValueError("evidence path must be relative")
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
                passed = False
                continue
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                passed = False
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
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
