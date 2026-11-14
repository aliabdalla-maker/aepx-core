#!/usr/bin/env python3
"""Bounded, offline, sequential acceptance regression runner. No mutations or deployment."""
import argparse
import json
import os
import re
import pathlib
import subprocess
import sys
import time
import signal

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", default="acceptance-100-iterations.json")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error("iterations must be between 1 and 100")
    records = []
    def persist():
        report = {"requested": args.iterations, "executed": len(records),
                  "all_passed": len(records) == args.iterations and all(x["passed"] for x in records),
                  "independent_acceptance_established": False,
                  "production_deployment_authorized": False, "runs": records}
        target = pathlib.Path(args.output)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        os.replace(temporary, target)
        return report

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    deadline = time.monotonic() + 3300  # Leave time for CI summary/artifact upload.
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests",
               "-p", "test_acceptance_evidence_integrity.py", "-v"]
    for iteration in range(1, args.iterations + 1):
        start = time.monotonic()
        remaining = deadline - start
        if remaining < 5:
            records.append({"iteration": iteration, "passed": False,
                            "error": "global 55-minute safety budget exhausted"})
            persist()
            break
        try:
            run = subprocess.run(command, capture_output=True, text=True,
                                 timeout=min(90, remaining), check=False,
                                 env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            output = run.stdout + run.stderr
            count = re.search(r"^Ran (\d+) tests? in ", output, re.MULTILINE)
            passed = (run.returncode == 0 and count is not None
                      and int(count.group(1)) >= 42
                      and re.search(r"^OK(?:\s|$)", output, re.MULTILINE) is not None)
            record = {"iteration": iteration, "passed": passed,
                      "tests_executed": int(count.group(1)) if count else None,
                      "return_code": run.returncode,
                      "elapsed_seconds": round(time.monotonic() - start, 3)}
            if not passed:
                record["diagnostic_tail"] = output[-12000:]
        except subprocess.TimeoutExpired as exc:
            record = {"iteration": iteration, "passed": False,
                      "error": "90-second per-iteration timeout"}
        records.append(record)
        persist()
        print(f"Iteration {iteration}/{args.iterations}: {'PASS' if record['passed'] else 'FAIL'}", flush=True)
        # Fail closed: do not repeat known failures 100 times without remediation.
        if not record["passed"]:
            break
    report = persist()
    return 0 if report["all_passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
