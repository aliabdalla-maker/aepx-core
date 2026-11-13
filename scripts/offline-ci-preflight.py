#!/usr/bin/env python3
"""Run the AEP-X workflow policy checks locally without GitHub Actions."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    [sys.executable, "scripts/check_workflow_integrity.py"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_workflow_deployment_policy.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_release_audit_workflow_policy.py", "-v"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_actions_queue_diagnostics_policy.py", "-v"],
]

def main():
    if importlib.util.find_spec("yaml") is None:
        print("ERROR: PyYAML is required; install with python -m pip install 'PyYAML>=6,<7'", file=sys.stderr)
        return 2
    failed = 0
    for command in CHECKS:
        print("+", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            failed += 1
            print(f"FAIL (exit {result.returncode})", file=sys.stderr, flush=True)
    print(f"Offline preflight: {len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
