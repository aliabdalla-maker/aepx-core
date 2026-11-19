"""Bounded supervised offline pilot: no LLM, network, auto-merge or deployment.

Run ONLY in a disposable OS-isolated sandbox. Test code is executable code.
"""
import argparse
import json
import time
from pathlib import Path
from aepx_autonomous_pilot import ALLOWED_PATTERNS, execute
from aepx_pilot_checkpoint import MAX_ITERATIONS, append, load, exclusive_checkpoint_lock

MAX_BATCH = 100

def run_batch(root, checkpoint, pattern, count, timeout, *, enabled=False, max_seconds=600):
    if enabled is not True:
        raise ValueError("batch execution requires explicit --execute")
    if type(count) is not int or not 1 <= count <= MAX_BATCH:
        raise ValueError("batch must be 1..100 attempts")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("invalid timeout")
    if type(max_seconds) is not int or not 1 <= max_seconds <= 3600:
        raise ValueError("invalid wall-clock limit")
    if pattern not in ALLOWED_PATTERNS:
        raise ValueError("test pattern not allowlisted")
    checkpoint = Path(checkpoint)
    if not checkpoint.is_absolute():
        raise ValueError("checkpoint must be an absolute path")
    # Hold a batch-level lock for the full test/record cycle. Other batch
    # processes using this controller cannot run ahead of the ledger.
    batch_lock = checkpoint.with_name(checkpoint.name + ".batch")
    with exclusive_checkpoint_lock(batch_lock):
        start = time.monotonic()
        initial_count = len(load(checkpoint)["attempts"])
        if initial_count + count > MAX_ITERATIONS:
            raise ValueError("batch would exceed the persistent iteration cap")
        results = []
        for _ in range(count):
            remaining = max_seconds - (time.monotonic() - start)
            if remaining < 1:
                break
            outcome = execute(root, pattern, timeout=min(timeout, max(1, int(remaining))), enabled=True)
            state = append(checkpoint, outcome)
            results.append({"attempt": len(state["attempts"]), "status": outcome["status"]})
            if outcome["status"] != "passed":
                break
        return {"initial_attempts": initial_count, "recorded": len(results),
                "results": results, "stopped": "failure" if results and results[-1]["status"] != "passed"
                else "time_limit" if len(results) < count else "completed",
                "release_approved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--pattern", required=True, choices=sorted(ALLOWED_PATTERNS))
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        if not 1 <= args.count <= MAX_BATCH:
            parser.error("count must be 1..100")
        print(json.dumps({"status":"dry-run", "count":args.count, "pattern":args.pattern,
                          "warning":"Explicit --execute required; run in a disposable sandbox."}))
        return
    report = run_batch(args.repo,args.checkpoint,args.pattern,args.count,args.timeout,
                       enabled=True,max_seconds=args.max_seconds)
    print(json.dumps(report, indent=2))
    if report["stopped"] != "completed":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
