"""Fail-closed, offline checkpoint controller for AEP-X autonomous iterations.

No API calls, shell execution, git writes, merges, deployments or cloud actions.
An external, separately authorized executor must implement actual engineering.
"""
import argparse
import json
import math
import os
import tempfile
from pathlib import Path

class RunnerDenied(ValueError):
    pass

FORBIDDEN = ("auto_merge", "auto_deploy", "external_mcp_execution", "chargeable_oci")

def validate_progress(data):
    if type(data) is not dict or data.get("schema_version") != 1:
        raise RunnerDenied("unsupported progress schema")
    iteration, maximum = data.get("iteration"), data.get("max_iterations")
    if (type(iteration) is not int or type(maximum) is not int
            or iteration < 0 or not 1 <= maximum <= 10000 or iteration > maximum):
        raise RunnerDenied("invalid iteration bounds")
    safety = data.get("safety")
    if type(safety) is not dict or any(safety.get(key) is not False for key in FORBIDDEN):
        raise RunnerDenied("privileged operations must remain disabled")
    if data.get("release_ready") is not False:
        raise RunnerDenied("runner cannot declare release readiness")
    return data

def next_checkpoint(data, *, outcome, evidence, max_spend_usd, spent_usd):
    validate_progress(data)
    if outcome not in ("passed", "blocked", "failed"):
        raise RunnerDenied("invalid outcome")
    if type(evidence) is not str or not evidence.strip() or len(evidence) > 2048:
        raise RunnerDenied("human-readable evidence required")
    if (type(max_spend_usd) not in (float, int) or type(spent_usd) not in (float, int)
            or not math.isfinite(float(spent_usd))
            or not math.isfinite(float(max_spend_usd))
            or not 0 <= spent_usd < max_spend_usd or max_spend_usd <= 0):
        raise RunnerDenied("invalid or exhausted spend budget")
    if data["iteration"] >= data["max_iterations"]:
        raise RunnerDenied("iteration limit reached")
    updated = dict(data)
    updated["iteration"] += 1
    updated["status"] = "checkpoint-" + outcome
    updated["last_evidence"] = evidence
    updated["spend_usd_recorded"] = float(spent_usd)
    updated["spend_usd_limit"] = float(max_spend_usd)
    return validate_progress(updated)

def atomic_save(path, data):
    validate_progress(data)
    path = Path(path)
    if not path.is_file():
        raise RunnerDenied("existing checkpoint file required")
    fd, temporary = tempfile.mkstemp(prefix=".aepx-checkpoint-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", default="docs/autonomous/PROGRESS.json")
    parser.add_argument("--outcome", choices=("passed", "failed", "blocked"))
    parser.add_argument("--evidence")
    parser.add_argument("--max-spend-usd", type=float)
    parser.add_argument("--spent-usd", type=float)
    args = parser.parse_args()
    with open(args.progress, encoding="utf-8") as handle:
        state = validate_progress(json.load(handle))
    if args.outcome is None:
        print(json.dumps(state, indent=2))
        return
    if args.evidence is None or args.max_spend_usd is None or args.spent_usd is None:
        parser.error("outcome requires evidence and explicit spend limit and amount")
    updated = next_checkpoint(state, outcome=args.outcome, evidence=args.evidence,
                              max_spend_usd=args.max_spend_usd, spent_usd=args.spent_usd)
    atomic_save(args.progress, updated)
    print(json.dumps({"iteration": updated["iteration"], "status": updated["status"]}))

if __name__ == "__main__":
    main()
