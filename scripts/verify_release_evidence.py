#!/usr/bin/env python3
"""Read-only GitHub Actions release evidence gate.

Requires a GitHub CLI authenticated session. No merge, deployment or secrets.
Fails closed on queued, missing, failed, stale or ambiguous workflow results.
"""
import argparse
import json
import subprocess
import sys

REQUIRED=("CI","HITL P0 acceptance")
def assess(runs,sha,required=REQUIRED):
    failures=[]
    for name in required:
        matching=[r for r in runs if r.get("name")==name
                  and r.get("headSha")==sha and r.get("event")=="push"]
        if not matching:
            failures.append(f"{name}: missing completed push run for target SHA")
            continue
        latest=max(matching,key=lambda r:r.get("runNumber",0))
        if latest.get("status")!="completed" or latest.get("conclusion")!="success":
            failures.append(f"{name}: {latest.get('status')}/{latest.get('conclusion')}")
    return failures

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",required=True)
    p.add_argument("--sha",required=True)
    p.add_argument("--required",nargs="+",default=list(REQUIRED))
    a=p.parse_args()
    if len(a.sha)!=40 or any(c not in "0123456789abcdef" for c in a.sha.lower()):
        p.error("--sha must be the complete 40-character commit SHA")
    if not a.required or len(set(a.required))!=len(a.required):
        p.error("required workflows must be unique and nonempty")
    try:
        raw=subprocess.check_output(
            ["gh","api",f"repos/{a.repo}/actions/runs","--paginate",
             "-f","per_page=100","-f",f"head_sha={a.sha}"],
            text=True,stderr=subprocess.PIPE,timeout=90)
        # --paginate may return multiple JSON objects; decode each in order.
        decoder=json.JSONDecoder()
        runs=[]
        pos=0
        while pos<len(raw):
            while pos<len(raw) and raw[pos].isspace():pos+=1
            if pos==len(raw):break
            obj,end=decoder.raw_decode(raw,pos)
            pos=end
            for x in obj.get("workflow_runs",[]):
                runs.append({"name":x.get("name"),"headSha":x.get("head_sha"),
                             "event":x.get("event"),"status":x.get("status"),
                             "conclusion":x.get("conclusion"),
                             "runNumber":x.get("run_number",0)})
        errors=assess(runs,a.sha,a.required)
    except (OSError,subprocess.SubprocessError,ValueError,KeyError) as exc:
        print(f"BLOCKED: cannot verify GitHub Actions evidence: {type(exc).__name__}",file=sys.stderr)
        return 2
    if errors:
        for issue in errors:print("BLOCKED:",issue)
        return 1
    print("PASS: required push workflows succeeded for exact commit SHA",a.sha)
    return 0
if __name__=="__main__":
    sys.exit(main())
