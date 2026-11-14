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
    seen_ids = set()
    valid_conclusions = {"success", "failure", "cancelled", "skipped",
                         "timed_out", "action_required", "neutral",
                         "stale", "startup_failure"}
    valid_statuses = {"queued", "waiting", "pending", "requested",
                      "in_progress", "completed", "action_required"}
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Malformed workflow run")
        status = run.get("status")
        if not isinstance(status, str) or status not in valid_statuses:
            raise ValueError("Missing or unknown workflow run status")
        run_id = run.get("databaseId")
        if run_id is not None:
            if type(run_id) is not int or run_id <= 0 or run_id in seen_ids:
                raise ValueError("Invalid or duplicate workflow run ID")
            seen_ids.add(run_id)
        name = run.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError("Malformed workflow name")
        if status != "completed" and run.get("conclusion") not in (None, ""):
            raise ValueError("Noncompleted workflow run has a conclusion")
        counts[status] = counts.get(status, 0) + 1
        if status == "completed":
            conclusion = run.get("conclusion")
            if not isinstance(conclusion, str) or conclusion not in valid_conclusions:
                raise ValueError("Completed workflow run has missing or unknown conclusion")
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
    if any(not name.strip() or name != name.strip() for name in args.require_workflow):
        parser.error("--require-workflow must be a nonempty workflow name")
    if len(args.require_workflow) != len(set(args.require_workflow)):
        parser.error("--require-workflow names must be unique")
    if args.require_success and (not args.head_sha or not args.require_workflow):
        parser.error("--require-success requires --head-sha and at least one --require-workflow")
    if args.head_sha and (len(args.head_sha) != 40 or
                          any(ch not in "0123456789abcdefABCDEF" for ch in args.head_sha)):
        parser.error("--head-sha must be a 40-character hexadecimal commit SHA")
    if (not args.repo or args.repo.strip() != args.repo or
            args.repo.count("/") != 1 or
            any(not part for part in args.repo.split("/"))):
        parser.error("--repo must be a nonempty owner/repository identifier")
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
            command.extend(["--commit", args.head_sha.lower()])
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
        if any(not isinstance(run.get("headSha"), str) or
               len(run["headSha"]) != 40 or
               any(ch not in "0123456789abcdefABCDEF" for ch in run["headSha"])
               for run in runs):
            print("Invalid GitHub Actions data: missing or malformed headSha", file=sys.stderr)
            return 2
        runs = [run for run in runs if run["headSha"].lower() == args.head_sha.lower()]
    try:
        report = summarize(runs)
    except ValueError as exc:
        print(f"Invalid GitHub Actions data: {exc}", file=sys.stderr)
        return 2
    required = sorted(set(args.require_workflow))
    if required and any(not isinstance(run.get("name"), str) or
                        not run["name"].strip() for run in runs):
        print("Invalid GitHub Actions data: missing workflow name", file=sys.stderr)
        return 2
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
