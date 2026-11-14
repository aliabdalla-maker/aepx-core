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
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Malformed workflow run")
        status = run.get("status")
        if not isinstance(status, str):
            raise ValueError("Missing workflow run status")
        counts[status] = counts.get(status, 0) + 1
        if status in ("queued", "waiting", "pending", "requested"):
            queued.append({"id": run.get("databaseId"), "name": run.get("name"),
                           "created_at": run.get("createdAt"), "status": status})
    return {"total": len(runs), "statuses": counts, "not_started": queued,
            "diagnosis": "Queue cause cannot be determined from run status alone"}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="aliabdalla-maker/aepx-core")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--input-json", help="Offline fixture; skip gh CLI")
    parser.add_argument("--fail-on-queued", action="store_true",
                        help="Exit 3 if any run is not started (for external monitoring)")
    args = parser.parse_args(argv)
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
    try:
        report = summarize(runs)
    except ValueError as exc:
        print(f"Invalid GitHub Actions data: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 3 if args.fail_on_queued and report["not_started"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
