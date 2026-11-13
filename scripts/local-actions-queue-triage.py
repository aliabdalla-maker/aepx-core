#!/usr/bin/env python3
"""Read-only Actions queue triage that runs locally without GitHub-hosted runners."""
import argparse
import collections
import datetime
import json
import subprocess
import sys
import urllib.error
import urllib.request


def fetch_json(url, token):
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "aepx-local-queue-triage",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def summarize(runs, now):
    counts = collections.Counter(run.get("status", "unknown") for run in runs)
    queued = []
    for run in runs:
        if run.get("status") != "queued":
            continue
        created = datetime.datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        queued.append({
            "id": run["id"],
            "name": run.get("name"),
            "url": run.get("html_url"),
            "age_minutes": max(0, int((now - created).total_seconds() // 60)),
        })
    return {"sample_size": len(runs), "status_counts": dict(counts), "queued": queued[:20]}


def runner_evidence(repo, queued, token, fetch=fetch_json):
    """Inspect up to five queued runs; do not infer why runners are unassigned."""
    evidence = []
    for run in queued[:5]:
        item = {"run_id": run["id"], "jobs": []}
        try:
            url = f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=20"
            jobs = fetch(url, token).get("jobs", [])
            for job in jobs[:20]:
                item["jobs"].append({
                    "name": job.get("name"),
                    "status": job.get("status"),
                    "labels": job.get("labels") or [],
                    "runner_assigned": job.get("runner_id") is not None,
                })
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            item["error_type"] = type(exc).__name__
        evidence.append(item)
    return evidence


def failed_before_jobs_evidence(repo, runs, token, fetch=fetch_json):
    """Sample completed failures with no job records, without inferring cause."""
    evidence = []
    failures = [run for run in runs
                if run.get("status") == "completed" and run.get("conclusion") == "failure"]
    for run in failures[:5]:
        item = {"run_id": run["id"], "name": run.get("name"),
                "url": run.get("html_url")}
        try:
            url = f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=20"
            jobs = fetch(url, token).get("jobs", [])
            item["job_count_in_first_page"] = len(jobs)
            item["no_jobs_returned"] = not bool(jobs)
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            item["error_type"] = type(exc).__name__
        evidence.append(item)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args(argv)
    if len(args.repo.split("/")) != 2 or any(not part for part in args.repo.split("/")):
        parser.error("--repo must be owner/repository")
    try:
        token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                               check=True, timeout=15).stdout.strip()
        if not token:
            raise RuntimeError("gh auth token returned no token")
        url = f"https://api.github.com/repos/{args.repo}/actions/runs?per_page=100"
        data = fetch_json(url, token)
        report = {"repository": args.repo, "sample_limit": 100,
                  **summarize(data.get("workflow_runs", []),
                              datetime.datetime.now(datetime.timezone.utc))}
        report["runner_assignment_sample"] = runner_evidence(args.repo, report["queued"], token)
        report["failed_run_job_sample"] = failed_before_jobs_evidence(args.repo, data.get("workflow_runs", []), token)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            from pathlib import Path
            Path(args.output).write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    except (OSError, subprocess.SubprocessError, urllib.error.URLError,
            ValueError, RuntimeError) as exc:
        print(f"ERROR: queue triage unavailable ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
