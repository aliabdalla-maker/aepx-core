"""Opt-in, offline AEP-X pilot test executor.

Only runs fixed unittest discovery in a supplied repository root.
Does not call an LLM, access GitHub, install packages, merge, deploy or modify OCI.
Run only in a disposable sandbox; repository tests are executable Python code.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ALLOWED_PATTERNS = frozenset({
    "test_aepx_autonomous_checkpoint.py",
    "test_mcp_egress_dns_policy.py",
    "test_mcp_egress_connection_admission.py",
    "test_mcp_http_preflight.py",
    "test_mcp_http_response_guard.py",
})
MAX_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 12000

class PilotDenied(ValueError):
    pass

def command_for(root, pattern):
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or pattern not in ALLOWED_PATTERNS:
        raise PilotDenied("unknown repository or test pattern")
    tests = root / "tests"
    if tests.is_symlink() or not tests.is_dir():
        raise PilotDenied("tests directory must be a real directory")
    target = tests / pattern
    if target.is_symlink() or not target.is_file() or target.resolve().parent != tests.resolve():
        raise PilotDenied("approved test file not found or unsafe")
    return [sys.executable, "-I", "-m", "unittest", "discover",
            "-s", str(tests), "-p", pattern, "-v"]

def execute(root, pattern, *, timeout=60, enabled=False):
    if enabled is not True:
        raise PilotDenied("execution requires explicit --execute")
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise PilotDenied("timeout outside safe range")
    command = command_for(root, pattern)
    safe_env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=str(Path(root).resolve()), env=safe_env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace",
                                timeout=timeout, shell=False, check=False)
        return {"pattern":pattern, "status":"passed" if result.returncode == 0 else "failed",
                "exit_code":result.returncode, "elapsed_seconds":round(time.monotonic()-start,2),
                "output":result.stdout[-MAX_OUTPUT_CHARS:]}
    except subprocess.TimeoutExpired as exc:
        return {"pattern":pattern, "status":"timeout", "exit_code":None,
                "elapsed_seconds":round(time.monotonic()-start,2),
                "output":str(exc)[-MAX_OUTPUT_CHARS:]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pattern", required=True, choices=sorted(ALLOWED_PATTERNS))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--checkpoint", default="", help="Optional local checkpoint ledger path")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status":"dry-run","command":command_for(args.repo,args.pattern),
                          "warning":"Run tests only inside a disposable sandbox."}, indent=2))
        return
    if args.checkpoint:
        from aepx_pilot_checkpoint import MAX_ITERATIONS, append, load, exclusive_checkpoint_lock
        checkpoint = Path(args.checkpoint)
        if not checkpoint.is_absolute():
            parser.error("checkpoint must be an absolute path")
        batch_lock = checkpoint.with_name(checkpoint.name + ".batch")
        with exclusive_checkpoint_lock(batch_lock):
            if len(load(checkpoint)["attempts"]) >= MAX_ITERATIONS:
                raise ValueError("iteration cap reached before execution")
            result = execute(args.repo,args.pattern,timeout=args.timeout,enabled=True)
            ledger = append(checkpoint, result)
            result["recorded_attempt"] = len(ledger["attempts"])
    else:
        result = execute(args.repo,args.pattern,timeout=args.timeout,enabled=True)
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
