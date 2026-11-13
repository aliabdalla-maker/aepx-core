#!/usr/bin/env python3
"""Run local workflow-policy checks and optionally emit machine-readable evidence."""
import argparse
import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    [sys.executable, "-m", "compileall", "-q", "scripts", "tests"],
    [sys.executable, "scripts/check_workflow_integrity.py"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_workflow_deployment_policy.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_release_audit_workflow_policy.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_actions_queue_diagnostics_policy.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_offline_ci_preflight.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_local_actions_queue_triage.py", "-v"],
]

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, help="Optional local JSON evidence file")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per check (default: 120)")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout must be a positive number")
    if importlib.util.find_spec("yaml") is None:
        print("ERROR: PyYAML is required; install with python -m pip install 'PyYAML>=6,<7'", file=sys.stderr)
        return 2
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                  capture_output=True, check=False, timeout=args.timeout)
        commit = revision.stdout.strip() if revision.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        commit = None
    evidence = {
        "schema_version": 1,
        "scope": "workflow-policy-only",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": commit,
        "checks": [],
    }
    for command in CHECKS:
        print("+", " ".join(command), flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False, timeout=args.timeout)
            exit_code = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
        except OSError as exc:
            exit_code = 127
            timed_out = False
            print(f"ERROR: check could not start: {type(exc).__name__}: {exc}", file=sys.stderr)
        evidence["checks"].append({
            "command": command[1:],
            "exit_code": exit_code,
            "passed": exit_code == 0,
            "timed_out": timed_out,
        })
        if exit_code:
            print(f"FAIL (exit {exit_code}; timed_out={timed_out})", file=sys.stderr, flush=True)
    passed = sum(check["passed"] for check in evidence["checks"])
    evidence["passed"] = passed
    evidence["total"] = len(CHECKS)
    evidence["overall_passed"] = passed == len(CHECKS)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence written: {args.json_output}")
    print(f"Offline preflight: {passed}/{len(CHECKS)} checks passed")
    return 0 if evidence["overall_passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
