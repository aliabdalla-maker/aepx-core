"""Generate and optionally execute a tightly bounded Docker test command.

Dry-run by default. Requires an explicitly trusted image digest and disposable
checkout. Docker isolation is defense-in-depth, not a proof of hostile-code safety.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

from aepx_autonomous_pilot import ALLOWED_PATTERNS, PilotDenied

DIGEST = re.compile(r"^python@sha256:[0-9a-f]{64}$")
CONTAINER_ROOT = "/workspace"
MAX_SECONDS = 120

def build_command(root, pattern, image, timeout=60):
    root = Path(root).resolve(strict=True)
    if pattern not in ALLOWED_PATTERNS:
        raise PilotDenied("test pattern not allowlisted")
    if not DIGEST.fullmatch(image):
        raise PilotDenied("image must be a pinned python sha256 digest")
    if type(timeout) is not int or not 1 <= timeout <= MAX_SECONDS:
        raise PilotDenied("timeout must be between 1 and 120 seconds")
    if not root.is_dir() or root.is_symlink() or not (root / "tests" / pattern).is_file():
        raise PilotDenied("trusted checkout and approved test file required")
    if (root / "tests").is_symlink() or (root / "tests" / pattern).is_symlink():
        raise PilotDenied("symlink test path forbidden")
    return [
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=512m", "--cpus=1",
        "--user=65534:65534", "--workdir="+CONTAINER_ROOT,
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777",
        "--mount=type=bind,src="+str(root)+",dst="+CONTAINER_ROOT+",readonly",
        "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTHONNOUSERSITE=1",
        image, "python", "-I", "-m", "unittest", "discover",
        "-s", "tests", "-p", pattern, "-v",
    ]

def run(root, pattern, image, *, timeout=60, execute=False):
    command = build_command(root, pattern, image, timeout)
    if execute is not True:
        return {"status":"dry-run", "command":command}
    try:
        proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace",
                              shell=False, timeout=timeout+15, check=False)
        return {"status":"passed" if proc.returncode == 0 else "failed",
                "exit_code":proc.returncode, "output":proc.stdout[-12000:]}
    except subprocess.TimeoutExpired:
        return {"status":"timeout", "exit_code":None,
                "warning":"Docker CLI timeout; verify and clean up any lingering container manually"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pattern", required=True, choices=sorted(ALLOWED_PATTERNS))
    parser.add_argument("--image", required=True, help="locally cached python@sha256 digest")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run(args.repo, args.pattern, args.image, timeout=args.timeout, execute=args.execute)
    print(json.dumps(result, indent=2))
    if args.execute and result["status"] != "passed":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
