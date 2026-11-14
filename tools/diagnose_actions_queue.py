#!/usr/bin/env python3
"""Read-only GitHub Actions queue diagnostics using the authenticated gh CLI."""
import argparse
import json
import subprocess
import sys

def summarize(runs):
    if not isinstance(runs, list):
        raise ValueError("GitHub Actions response must be a list")
    counts = {}
    queued = []
    conclusions = {}
    unsuccessful = []
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Malformed workflow run")
        status = run.get("status")
        if not isinstance(status, str):
            raise ValueError("Missing workflow run status")
        counts[status] = counts.get(status, 0) + 1
        if status == "completed":
            conclusion = run.get("conclusion")
            if not isinstance(conclusion, str) or not conclusion:
                raise ValueError("Completed workflow run lacks a conclusion")
            conclusions[conclusion] = conclusions.get(conclusion, 0) + 1
            if conclusion != "success":
                unsuccessful.append({"id": run.get("databaseId"),
                                     "name": run.get("name"), "conclusion": conclusion})
        if status in ("queued", "waiting", "pending", "requested"):
            queued.append({"id": run.get("databaseId"), "name": run.get("name"),
                           "created_at": run.get("createdAt"), "status": status})
    return {"total": len(runs), "statuses": counts,
            "conclusions": conclusions, "unsuccessful": unsuccessful,
            "not_started": queued,
            "diagnosis": "Queue cause cannot be determined from run status alone"}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="aliabdalla-maker/aepx-core")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--input-json", help="Offline fixture; skip gh CLI")
    parser.add_argument("--head-sha", help="Restrict snapshot to one exact commit SHA")
    parser.add_argument("--require-workflow", action="append", default=[],
                        help="Require an exact workflow name in the queried snapshot; repeatable")
    parser.add_argument("--require-success", action="store_true",
                        help="Exit 4 unless every queried run completed successfully")
    parser.add_argument("--fail-on-queued", action="store_true",
                        help="Exit 3 if any run is not started (for external monitoring)")
    args = parser.parse_args(argv)
    if any(not name.strip() for name in args.require_workflow):
        parser.error("--require-workflow must be a nonempty workflow name")
    if args.require_success and (not args.head_sha or not args.require_workflow):
        parser.error("--require-success requires --head-sha and at least one --require-workflow")
    if args.head_sha and (len(args.head_sha) != 40 or
                          any(ch not in "0123456789abcdefABCDEF" for ch in args.head_sha)):
        parser.error("--head-sha must be a 40-character hexadecimal commit SHA")
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    if args.input_json:
        try:
            with open(args.input_json, encoding="utf-8") as handle:
                runs = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"Unable to read offline fixture: {type(exc).__name__}", file=sys.stderr)
            return 2
    else:
        command = ["gh", "run", "list", "--repo", args.repo, "--limit",
                   str(args.limit), "--json",
                   "databaseId,name,status,conclusion,headSha,createdAt"]
        if args.head_sha:
            command.extend(["--commit", args.head_sha])
        try:
            result = subprocess.run(command, check=True, capture_output=True,
                                    text=True, timeout=30)
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            print(f"Unable to query GitHub Actions: {type(exc).__name__}", file=sys.stderr)
            return 2
        try:
            runs = json.loads(result.stdout)
        except json.JSONDecodeError:
            print("GitHub CLI returned invalid JSON", file=sys.stderr)
            return 2
    snapshot_count = len(runs) if isinstance(runs, list) else 0
    if args.head_sha:
        if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
            print("Invalid GitHub Actions data: expected run records", file=sys.stderr)
            return 2
        runs = [run for run in runs if run.get("headSha") == args.head_sha]
    try:
        report = summarize(runs)
    except ValueError as exc:
        print(f"Invalid GitHub Actions data: {exc}", file=sys.stderr)
        return 2
    required = sorted(set(args.require_workflow))
    if args.require_success and snapshot_count >= args.limit:
        print("Strict acceptance snapshot reached --limit; increase the limit to establish coverage", file=sys.stderr)
        return 6
    observed = {run.get("name") for run in runs}
    missing = [name for name in required if name not in observed]
    report["required_workflows"] = required
    report["missing_workflows"] = missing
    print(json.dumps(report, indent=2))
    if missing:
        return 5
    if args.require_success and (report["total"] == 0 or
                                 report["statuses"].get("completed", 0) != report["total"] or
                                 report["unsuccessful"]):
        return 4
    return 3 if args.fail_on_queued and report["not_started"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
