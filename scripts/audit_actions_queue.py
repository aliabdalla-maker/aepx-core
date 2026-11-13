#!/usr/bin/env python3
"""Read-only GitHub Actions queue diagnostic. No secrets or mutations."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

def inspect_runs(repo, token=None, per_page=100):
    if not repo or "/" not in repo or repo.count("/")!=1:
        raise ValueError("owner/repo required")
    url=f"https://api.github.com/repos/{repo}/actions/runs?per_page={per_page}"
    headers={"Accept":"application/vnd.github+json",
             "User-Agent":"aepx-actions-queue-audit",
             "X-GitHub-Api-Version":"2022-11-28"}
    if token:
        headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=15) as response:
        payload=json.load(response)
    runs=payload.get("workflow_runs",[])
    now=datetime.now(timezone.utc)
    summary={"repository":repo,"sample_size":len(runs),
             "total_count":payload.get("total_count"),
             "status_counts":{},"queued_over_30_minutes":[],
             "warning":"First page only; no workflow conclusions are inferred from queued runs."}
    for run in runs:
        status=run.get("status","unknown")
        summary["status_counts"][status]=summary["status_counts"].get(status,0)+1
        if status=="queued":
            created=run.get("created_at")
            if created:
                try:
                    age=(now-datetime.fromisoformat(created.replace("Z","+00:00"))).total_seconds()/60
                except (TypeError,ValueError):
                    continue
                if age>30:
                    summary["queued_over_30_minutes"].append({
                        "id":run.get("id"),"name":run.get("name"),
                        "minutes_queued":round(age,1),"url":run.get("html_url")})
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",default="aliabdalla-maker/aepx-core")
    args=parser.parse_args()
    try:
        result=inspect_runs(args.repo,token=os.getenv("GITHUB_TOKEN"))
    except (ValueError,urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
        print(json.dumps({"error":type(exc).__name__,
                          "message":"GitHub Actions read failed; verify access, token scopes and network."}),
              file=sys.stderr)
        return 2
    print(json.dumps(result,indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
