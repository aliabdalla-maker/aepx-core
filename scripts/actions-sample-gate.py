#!/usr/bin/env python3
"""Fail-closed evaluation of sampled Actions evidence; never authorizes deployment."""
import argparse
import json
from pathlib import Path


def evaluate(report):
    errors = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    sample = report.get("sample_size")
    counts = report.get("conclusion_counts")
    if type(sample) is not int or sample < 1:
        errors.append("missing or empty workflow sample")
    if not isinstance(counts, dict):
        errors.append("missing conclusion_counts")
        return errors
    if any(type(v) is not int or v < 0 for v in counts.values()):
        errors.append("invalid conclusion count")
    if type(sample) is int and sum(counts.values()) != sample:
        errors.append("conclusion counts do not match sample")
    if counts.get("failure", 0) or counts.get("cancelled", 0):
        errors.append("failed or cancelled runs present")
    if counts.get("not_completed", 0):
        errors.append("unfinished runs present")
    if counts.get("success", 0) < 1:
        errors.append("no successful runs in sample")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: unreadable evidence ({type(exc).__name__})")
        return 2
    errors = evaluate(report)
    for error in errors:
        print(f"BLOCKED: {error}")
    if errors:
        return 1
    print("SAMPLE HEALTHY: no sampled failures; mandatory release gates still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
