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
                  "production_deployment_authorized": False,
                  "source_commit": os.environ.get("GITHUB_SHA"),
                  "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
                  "runs": records}
        target = pathlib.Path(args.output)
        # Do not follow symlinked output directories when persisting CI evidence.
        if any(parent.is_symlink() for parent in target.parents):
            raise OSError("refusing symlinked report parent directory")
        if target.is_symlink():
            raise OSError("refusing symlink report destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in target.parents):
            raise OSError("refusing symlinked report parent directory")
        if target.is_symlink():
            raise OSError("refusing symlink report destination")
        if target.exists() and not target.is_file():
            raise OSError("refusing non-file report destination")
        # Use a unique temporary file to prevent stale or concurrent .tmp collisions.
        import tempfile
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False
            ) as handle:
                temp_path = pathlib.Path(handle.name)
                json.dump(report, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return report

    interrupted = False

    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True
        raise KeyboardInterrupt

    previous_sigterm = signal.signal(signal.SIGTERM, stop)
    deadline = time.monotonic() + 3300  # Leave time for CI summary/artifact upload.
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests",
               "-p", "test_acceptance_evidence_integrity.py", "-v"]
    try:
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
                # unittest writes its completion summary to stderr by default.
                # Check that stream alone to avoid forged success text on stdout.
                summary_output = run.stderr
                # Require a terminal unittest summary, not an arbitrary embedded OK.
                summary = re.search(
                    r"(?m)^Ran (\d+) tests? in [^\r\n]+\r?\n[ \t]*\r?\nOK\r?\n?\Z",
                    summary_output,
                )
                count = summary
                passed = (run.returncode == 0 and summary is not None
                          and int(summary.group(1)) >= 42)
                record = {"iteration": iteration, "passed": passed,
                          "tests_executed": int(count.group(1)) if count else None,
                          "return_code": run.returncode,
                          "elapsed_seconds": round(time.monotonic() - start, 3)}
                if not passed:
                    record["diagnostic_tail"] = output[-12000:]
            except subprocess.TimeoutExpired:
                record = {"iteration": iteration, "passed": False,
                          "error": "per-iteration execution timeout"}
            except (OSError, subprocess.SubprocessError) as exc:
                record = {"iteration": iteration, "passed": False,
                          "error": f"test process failed to start or execute: {type(exc).__name__}"}
            except Exception as exc:
                record = {"iteration": iteration, "passed": False,
                          "error": f"unexpected runner exception: {type(exc).__name__}"}
            except KeyboardInterrupt:
                record = {"iteration": iteration, "passed": False,
                          "error": "runner interrupted before cycle completed"}
                records.append(record)
                persist()
                print(f"Iteration {iteration}/{args.iterations}: INTERRUPTED", flush=True)
                return 130
            records.append(record)
            persist()
            print(f"Iteration {iteration}/{args.iterations}: {'PASS' if record['passed'] else 'FAIL'}", flush=True)
            # Fail closed: do not repeat known failures 100 times without remediation.
            if not record["passed"]:
                break
        report = persist()
        return 0 if report["all_passed"] and not interrupted else 1

    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)

if __name__ == "__main__":
    raise SystemExit(main())
