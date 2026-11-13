#!/usr/bin/env python3
"""Read-only GitHub Actions queue diagnostics; never modifies runs or settings."""
import argparse
import json
import subprocess
import sys
from datetime import datetime,timezone

def diagnose(runs,jobs,now,threshold_minutes=15):
    findings=[]
    for run in runs:
        rid=run["id"]
        pending=[j for j in jobs.get(rid,[]) if j.get("status")=="queued"]
        if not pending:
            continue
        stamp=run.get("created_at")
        try:
            created=datetime.fromisoformat(stamp.replace("Z","+00:00"))
            age=max(0,(now-created).total_seconds()/60)
        except (AttributeError,TypeError,ValueError):
            age=None
        findings.append({"run_id":rid,"workflow":run.get("name"),
                         "status":run.get("status"),"queued_jobs":[j.get("name") for j in pending],
                         "age_minutes":round(age,1) if age is not None else None,
                         "stale":age is None or age>=threshold_minutes})
    return findings

def gh_get(path):
    output=subprocess.check_output(["gh","api","-X","GET",path],
                                   text=True,stderr=subprocess.PIPE,timeout=45)
    return json.loads(output)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--sha",required=True)
    p.add_argument("--threshold-minutes",type=int,default=15)
    a=p.parse_args()
    if len(a.sha)!=40 or any(c not in "0123456789abcdef" for c in a.sha.lower()):
        p.error("complete 40-character SHA required")
    if a.threshold_minutes<1:p.error("threshold must be positive")
    try:
        response=gh_get(f"repos/{a.repo}/actions/runs?head_sha={a.sha}&per_page=100")
        runs=response["workflow_runs"]
        if not isinstance(runs,list):raise ValueError("invalid run response")
        jobs={}
        for run in runs:
            if run.get("status") in ("queued","in_progress","waiting","pending"):
                rid=run["id"]
                data=gh_get(f"repos/{a.repo}/actions/runs/{rid}/jobs?per_page=100")
                jobs[rid]=data["jobs"]
        findings=diagnose(runs,jobs,datetime.now(timezone.utc),a.threshold_minutes)
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError) as exc:
        print(f"UNKNOWN: could not verify queue state ({type(exc).__name__})",file=sys.stderr)
        return 2
    print(json.dumps({"sha":a.sha,"runs_checked":len(runs),"queued":findings},
                     indent=2,sort_keys=True))
    if any(x["stale"] for x in findings):
        print("BLOCKED: investigate Actions permissions, runner availability, quotas and billing")
        return 1
    return 0

if __name__=="__main__":
    sys.exit(main())
