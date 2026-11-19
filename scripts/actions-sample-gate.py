#!/usr/bin/env python3
"""Fail-closed evaluation of sampled Actions evidence; never authorizes deployment."""
import argparse
import json
from datetime import datetime
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
    allowed = {"success", "failure", "cancelled", "not_completed"}
    unknown = set(counts) - allowed
    if unknown:
        errors.append("unknown conclusions: " + ", ".join(sorted(unknown)))
    statuses = report.get("status_counts")
    if not isinstance(statuses, dict):
        errors.append("missing status_counts")
    else:
        valid_statuses = {"queued", "in_progress", "pending", "waiting", "requested", "completed"}
        if set(statuses) - valid_statuses:
            errors.append("unknown workflow statuses")
        if any(type(v) is not int or v < 0 for v in statuses.values()):
            errors.append("invalid status count")
        if type(sample) is int and sum(statuses.values()) != sample:
            errors.append("status counts do not match sample")
        if statuses.get("completed", 0) != sample:
            errors.append("not all sampled runs completed")
    if counts.get("failure", 0) or counts.get("cancelled", 0):
        errors.append("failed or cancelled runs present")
    if counts.get("not_completed", 0):
        errors.append("unfinished runs present")
    if counts.get("success", 0) < 1:
        errors.append("no successful runs in sample")
    return errors


def valid_run_order(run):
    """Reject malformed or ambiguous metadata before comparing run ordering."""
    if type(run.get("id")) is not int or run["id"] <= 0:
        return False
    if type(run.get("run_attempt")) is not int or run["run_attempt"] <= 0:
        return False
    created = run.get("created_at")
    if not isinstance(created, str):
        return False
    try:
        parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def run_order(run):
    return (datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")),
            run["run_attempt"], run["id"])


def evaluate_required(report, sha, workflows):
    """Verify each required workflow has a successful completed run on exact SHA."""
    if not isinstance(report, dict) or not isinstance(report.get("runs"), list):
        return ["missing run-level evidence"]
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in sha):
        return ["--sha must be a 40-character commit SHA"]
    if not workflows:
        return ["at least one required workflow must be specified"]
    errors = []
    # Triage emits newest-first API results. Never accept a stale passing run
    # when a later retry for the same workflow and SHA is queued or failed.
    for workflow in workflows:
        matches = [run for run in report["runs"]
                   if isinstance(run, dict) and run.get("head_sha") == sha
                   and run.get("workflow_path") == workflow]
        if not matches:
            errors.append(f"missing required workflow: {workflow} at {sha}")
        elif not all(valid_run_order(run) for run in matches):
            errors.append(f"missing run ordering evidence: {workflow} at {sha}")
        elif len({run["id"] for run in matches}) != len(matches):
            errors.append(f"duplicate run IDs in evidence: {workflow} at {sha}")
        elif any(run.get("status") not in ("completed", "queued", "pending",
                                          "in_progress", "waiting", "requested")
                 or run.get("conclusion") not in (None, "success", "failure",
                                                   "cancelled", "skipped",
                                                   "timed_out", "action_required",
                                                   "neutral", "stale",
                                                   "startup_failure") for run in matches):
            errors.append(f"unrecognized run status or conclusion: {workflow} at {sha}")
        else:
            latest = max(matches, key=run_order)
            if latest.get("status") != "completed" or latest.get("conclusion") != "success":
                errors.append(f"required workflow not successful: {workflow} at {sha}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--sha", help="Exact 40-character target commit SHA")
    parser.add_argument("--require-workflow", action="append", default=[],
                        help="Exact workflow path; repeat for each required workflow")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: unreadable evidence ({type(exc).__name__})")
        return 2
    errors = evaluate_required(report, args.sha, args.require_workflow) if (args.sha or args.require_workflow) else evaluate(report)
    for error in errors:
        print(f"BLOCKED: {error}")
    if errors:
        return 1
    print("EVIDENCE HEALTHY: requested checks passed in supplied sample; release approval still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
