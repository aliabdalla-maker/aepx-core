#!/usr/bin/env python3
"""Fail-closed offline validator for the 100-cycle evidence report."""
import argparse
import json
import math
import os
import re
import stat
from pathlib import Path


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def verify(path, commit, run_id, expected=100, minimum_tests=42):
    source = Path(path)
    if source.is_symlink() or any(parent.is_symlink() for parent in source.parents):
        raise ValueError("symlinked evidence path is not permitted")
    if not source.is_file():
        raise ValueError("missing or non-file evidence report")
    metadata = source.stat()
    if metadata.st_nlink != 1:
        raise ValueError("hardlinked evidence report is not permitted")
    if metadata.st_size > 2_000_000:
        raise ValueError("oversized evidence report")
    # Read through a no-follow descriptor to reject final-component symlink swaps.
    if not isinstance(getattr(os, "O_NOFOLLOW", None), int):
        raise ValueError("platform lacks required no-follow evidence protection")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    descriptor = os.open(source, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_size > 2_000_000:
            raise ValueError("unsafe or oversized opened evidence report")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            report = json.load(handle, object_pairs_hook=_unique,
                               parse_constant=_invalid_constant)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(report, dict):
        raise ValueError("report must be an object")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("valid 40-character commit SHA required")
    if not isinstance(run_id, str) or not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("valid numeric workflow run ID required")
    required = {"source_commit", "workflow_run_id", "requested", "executed", "all_passed",
                "independent_acceptance_established", "production_deployment_authorized", "runs"}
    if set(report) != required:
        raise ValueError("unexpected or missing report fields")
    if report.get("source_commit") != commit or report.get("workflow_run_id") != run_id:
        raise ValueError("report provenance mismatch")
    if (type(report.get("requested")) is not int or report["requested"] != expected
            or type(report.get("executed")) is not int or report["executed"] != expected):
        raise ValueError("incorrect cycle count")
    if report.get("all_passed") is not True:
        raise ValueError("cycles have not all passed")
    if report.get("independent_acceptance_established") is not False:
        raise ValueError("independent acceptance must remain unestablished")
    if report.get("production_deployment_authorized") is not False:
        raise ValueError("production deployment must remain unauthorized")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != expected:
        raise ValueError("missing cycle records")
    for number, cycle in enumerate(runs, 1):
        if not isinstance(cycle, dict):
            raise ValueError(f"cycle {number} is not an object")
        if set(cycle) != {"iteration", "passed", "tests_executed", "return_code", "elapsed_seconds"}:
            raise ValueError(f"unexpected or missing cycle {number} fields")
        elapsed = cycle.get("elapsed_seconds")
        if (type(cycle.get("iteration")) is not int or cycle["iteration"] != number
                or cycle.get("passed") is not True
                or type(cycle.get("tests_executed")) is not int
                or cycle["tests_executed"] < minimum_tests
                or type(cycle.get("return_code")) is not int or cycle["return_code"] != 0
                or type(elapsed) not in (float, int)
                or not math.isfinite(elapsed) or not 0 <= elapsed <= 95):
            raise ValueError(f"invalid cycle {number}")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--commit", default=os.getenv("GITHUB_SHA"))
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID"))
    parser.add_argument("--expected", type=int, default=100)
    args = parser.parse_args()
    try:
        verify(args.report, args.commit, args.run_id, args.expected)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Invalid acceptance evidence: {exc}\n")
    print("Offline cycle evidence verified; independent acceptance NOT ESTABLISHED.")


if __name__ == "__main__":
    main()
