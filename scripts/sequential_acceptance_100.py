#!/usr/bin/env python3
"""Sequential, fail-fast 100-pass AEP-X acceptance runner.

No automatic code edits, PR merges, network tool calls or deployments.
Each pass runs one subprocess, waits for completion, records a result and
stops immediately on failure. Intended for an isolated CI checkout.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def run(count,command,report):
    if not 1<=count<=100:
        raise ValueError("count must be 1..100")
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    completed=0
    for index in range(1,count+1):
        start=time.monotonic()
        try:
            result=subprocess.run(command,check=False,timeout=600)
            code=result.returncode
        except subprocess.TimeoutExpired:
            code=124
        completed=index
        record={"iteration":index,"total":count,"exit_code":code,
                "elapsed_seconds":round(time.monotonic()-start,3),
                "outcome":"pass" if code==0 else "fail"}
        with report.open("a",encoding="utf-8") as out:
            out.write(json.dumps(record,sort_keys=True)+"\n")
        print(f"Iteration {index}/{count}: {record['outcome']}",flush=True)
        if code:
            print("Stopped at first failure; investigate and fix before rerunning.",file=sys.stderr)
            return code
    print(f"Completed {completed}/{count} sequential passes. No changes deployed.")
    return 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--count",type=int,default=100)
    parser.add_argument("--report",default="artifacts/sequential-acceptance.jsonl")
    args=parser.parse_args()
    if os.getenv("AEPX_SEQUENTIAL_ACCEPTANCE_APPROVED")!="yes":
        parser.error("AEPX_SEQUENTIAL_ACCEPTANCE_APPROVED=yes is required")
    cmd=[sys.executable,"-m","pytest","-q","tests/test_hitl_remote_reconciliation.py",
         "tests/test_hitl_execution_receipts.py","tests/test_hitl_health.py"]
    return run(args.count,cmd,args.report)

if __name__=="__main__":
    sys.exit(main())
