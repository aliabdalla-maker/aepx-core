#!/usr/bin/env python3
"""Read-only GitHub Actions queue report; does not require a runner to execute."""
import argparse
import datetime
import json
import os
import urllib.request

API = "https://api.github.com/repos"

def get_json(url, token):
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "aepx-queue-inspector"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)

def inspect(repo, token, get=get_json, now=None):
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    data = get(f"{API}/{repo}/actions/runs?per_page=100", token)
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise ValueError("invalid Actions runs response")
    runs = data["workflow_runs"]
    if any(not isinstance(run, dict) for run in runs):
        raise ValueError("invalid Actions run record")
    result = {"repository": repo, "sample_size": len(runs),
              "sample_limit": 100, "status_counts": {}, "queued": [],
              "diagnosis": "UNDETERMINED", "release_approved": False,
              "sample_truncated": len(runs) == 100}
    for run in runs:
        status = run.get("status", "unknown")
        result["status_counts"][status] = result["status_counts"].get(status, 0) + 1
        if status != "queued" or len(result["queued"]) >= 10:
            continue
        run_id = run.get("id")
        stamp = run.get("created_at")
        if type(run_id) is not int or run_id <= 0 or not isinstance(stamp, str):
            raise ValueError("invalid queued run metadata")
        created = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("queued run timestamp lacks timezone")
        jobs_data = get(f"{API}/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
        if not isinstance(jobs_data, dict) or not isinstance(jobs_data.get("jobs"), list):
            raise ValueError("invalid Actions jobs response")
        jobs = jobs_data["jobs"]
        if any(not isinstance(job, dict) for job in jobs):
            raise ValueError("invalid Actions job record")
        for job in jobs:
            if type(job.get("id")) is not int or job["id"] <= 0:
                raise ValueError("invalid job id")
            if not isinstance(job.get("labels"), list) or any(
                    not isinstance(label, str) for label in job["labels"]):
                raise ValueError("invalid runner labels")
        result["queued"].append({
            "run_id": run_id, "workflow": run.get("name"),
            "age_minutes": max(0, int((now - created).total_seconds() // 60)),
            "jobs": [{"id": job["id"], "name": job.get("name"), "status": job.get("status"),
                      "labels": job.get("labels"), "runner_assigned": job.get("runner_id") is not None}
                     for job in jobs]})
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN")
    if not token:
        parser.error("GH_TOKEN required; use a read-only Actions token")
    try:
        report = inspect(args.repo, token)
        rendered = json.dumps(report, indent=2) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as stream:
                stream.write(rendered)
        print(rendered)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"BLOCKED: diagnostic evidence unavailable ({type(exc).__name__})\n")

if __name__ == "__main__":
    main()
