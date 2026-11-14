#!/usr/bin/env python3
"""Fetch exact-SHA GitHub Actions evidence; fail closed without approving releases."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime

REQUIRED = (
    ".github/workflows/ci.yml",
    ".github/workflows/mcp-disposable-postgres.yml",
    ".github/workflows/hitl-acceptance.yml",
    ".github/workflows/aepx-release-readiness.yml",
)

def fetch_branch_sha(repo, token, fetch=None):
    if fetch is None:
        def fetch(url):
            request = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "aepx-release-evidence-gate"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
    data = fetch(f"https://api.github.com/repos/{repo}/branches/master")
    if not isinstance(data, dict) or not isinstance(data.get("commit"), dict):
        raise ValueError("invalid master branch response")
    sha = data["commit"].get("sha")
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in sha):
        raise ValueError("invalid master branch SHA")
    return sha.lower()

def fetch_runs(repo, sha, token, fetch=None):
    if fetch is None:
        def fetch(url):
            request = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "aepx-release-evidence-gate"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
    runs = []
    expected_total = None
    for page in range(1, 11):
        url = (f"https://api.github.com/repos/{repo}/actions/runs"
               f"?head_sha={sha}&per_page=100&page={page}")
        data = fetch(url)
        if not isinstance(data, dict):
            raise ValueError("malformed API page")
        total = data.get("total_count")
        if type(total) is not int or total < 0:
            raise ValueError("missing or invalid total_count")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ValueError("total_count changed during pagination")
        batch = data.get("workflow_runs")
        if not isinstance(batch, list):
            raise ValueError("missing workflow_runs")
        if any(not isinstance(item, dict) for item in batch):
            raise ValueError("malformed run record")
        runs.extend(batch)
        if len(runs) > expected_total:
            raise ValueError("more runs than total_count")
        if len(batch) < 100:
            if len(runs) != expected_total:
                raise ValueError("incomplete evidence pagination")
            return runs
    raise ValueError("workflow evidence pagination limit reached; fail closed")

def valid_metadata(run):
    if type(run.get("id")) is not int or run["id"] <= 0:
        return False
    if type(run.get("run_attempt")) is not int or run["run_attempt"] <= 0:
        return False
    stamp = run.get("created_at")
    if not isinstance(stamp, str):
        return False
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None

def evaluate(runs, sha, required=REQUIRED, repository="aliabdalla-maker/aepx-core", branch="master"):
    if not isinstance(runs, list) or any(not isinstance(item, dict) for item in runs):
        return ["INVALID_EVIDENCE_COLLECTION"]
    errors = []
    for workflow in required:
        matching = [r for r in runs if r.get("head_sha") == sha
                    and r.get("path") == workflow]
        if not matching:
            errors.append(f"MISSING {workflow}")
            continue
        if any(r.get("event") not in ("push", "workflow_dispatch")
               or r.get("head_branch") != branch
               or not isinstance(r.get("head_repository"), dict)
               or r["head_repository"].get("full_name") != repository
               for r in matching):
            errors.append(f"INVALID_PROVENANCE {workflow}")
            continue
        if any(not valid_metadata(r) for r in matching):
            errors.append(f"INVALID_METADATA {workflow}")
            continue
        ids = [r["id"] for r in matching]
        if len(ids) != len(set(ids)):
            errors.append(f"DUPLICATE_RUN {workflow}")
            continue
        # API run IDs are monotonically increasing; attempts distinguish reruns.
        latest = max(matching, key=lambda r: (r["id"], r["run_attempt"]))
        if latest.get("status") != "completed" or latest.get("conclusion") != "success":
            errors.append(f"NOT_SUCCESSFUL {workflow}: {latest.get('status')}/{latest.get('conclusion')}")
    return errors

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    if args.repo != os.environ.get("GITHUB_REPOSITORY", args.repo):
        parser.error("repository must match GitHub Actions repository")
    if len(args.sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in args.sha):
        parser.error("SHA must be 40 hexadecimal characters")
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("BLOCKED: GH_TOKEN unavailable", file=sys.stderr)
        return 2
    try:
        before = fetch_branch_sha(args.repo, token)
        if before != args.sha.lower():
            raise ValueError("target SHA is not current master")
        runs = fetch_runs(args.repo, args.sha, token)
        after = fetch_branch_sha(args.repo, token)
        if after != before:
            raise ValueError("master changed while gathering evidence")
        errors = evaluate(runs, args.sha, repository=args.repo)
        result = {"repository": args.repo, "sha": args.sha, "required": list(REQUIRED),
                  "sample_size": len(runs), "blockers": errors,
                  "release_approved": False}
        rendered = json.dumps(result, indent=2) + "\n"
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(rendered, encoding="utf-8")
        print(rendered)
        return 1 if errors else 0
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        print(f"BLOCKED: evidence unavailable ({type(exc).__name__})", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
