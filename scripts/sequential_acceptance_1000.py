#!/usr/bin/env python3
"""Run ten 100-pass offline acceptance batches in strict numeric order.

Never edits code, dispatches workflows, merges PRs or deploys services.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def run_batches(*, batches=10, batch_size=100, report_dir="artifacts/sequential-1000",
                python=sys.executable, runner="scripts/sequential_acceptance_100.py"):
    if not (1 <= batches <= 10 and 1 <= batch_size <= 100):
        raise ValueError("batches must be 1..10 and batch_size must be 1..100")
    if os.getenv("AEPX_SEQUENTIAL_ACCEPTANCE_APPROVED") != "yes":
        raise PermissionError("explicit offline acceptance approval required")
    dest=Path(report_dir)
    dest.mkdir(parents=True,exist_ok=True)
    summary=dest/"summary.jsonl"
    if summary.exists() or any(dest.glob("batch-*.jsonl")):
        raise FileExistsError("reports already exist: choose a fresh report directory")
    for batch in range(1,batches+1):
        report=dest/f"batch-{batch:02d}.jsonl"
        started=time.monotonic()
        try:
            completed=subprocess.run([python,runner,"--count",str(batch_size),
                                      "--report",str(report)],check=False,timeout=10800)
            exit_code=completed.returncode
        except subprocess.TimeoutExpired:
            exit_code=124
        records=[]
        if report.exists():
            try:
                records=[json.loads(line) for line in report.read_text().splitlines()]
            except (ValueError,UnicodeError):
                exit_code=1
        valid=(exit_code==0 and len(records)==batch_size and all(
            x.get("iteration")==i and x.get("total")==batch_size and
            x.get("exit_code")==0 and x.get("outcome")=="pass"
            for i,x in enumerate(records,1)))
        result={"batch":batch,"expected":batch_size,"verified":len(records) if valid else 0,
                "outcome":"pass" if valid else "fail","exit_code":exit_code,
                "elapsed_seconds":round(time.monotonic()-started,3)}
        with summary.open("a",encoding="utf-8") as out:
            out.write(json.dumps(result,sort_keys=True)+"\n")
        print(f"Batch {batch}/{batches}: {result['outcome']}",flush=True)
        if not valid:
            print("Stopped on first incomplete or failed batch",file=sys.stderr)
            return 1
    print(f"Verified {batches*batch_size} sequential offline test passes")
    return 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--report-dir",default="artifacts/sequential-1000")
    args=parser.parse_args()
    return run_batches(report_dir=args.report_dir)
if __name__=="__main__":
    sys.exit(main())
