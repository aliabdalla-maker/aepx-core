#!/usr/bin/env python3
"""Post-deploy and post-release smoke test (RA-03, RA-11, REL-01, AV-01 delivery, FN-06).

Checks, in order, and stops at nothing: every check is reported, and the exit code is non-zero if any failed.
  1. /health is up and reports the expected version (and build SHA when given)
  2. /ready is all-green and a detection bundle is published (FN-06)
  3. a protected route refuses an unauthenticated request (401)
  4. the GitHub release exists, every asset listed in SHA256SUMS.txt is attached, and a sample of
     assets (or all with --all-assets) download and match their SHA-256 (none is the empty-file hash)

Writes a JSON evidence record (--evidence) for docs/evidence. Standard library only.

  python tools/smoke_release.py --version 0.1.2 --tag aav-v0.1.2 \
      --api https://api.softwareequality.com/apps/agentic-antivirus/api --evidence smoke-0.1.2.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
DEFAULT_API = "https://api.softwareequality.com/apps/agentic-antivirus/api"
REPO = "aliabdalla-maker/aepx-core"


def fetch(url: str, timeout: float = 30.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "aav-smoke/1", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(getattr(e, "reason", e)).encode()


class Run:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "passed": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")
        return ok

    @property
    def passed(self) -> bool:
        return all(c["passed"] for c in self.checks)


def check_api(run: Run, api: str, version: str, build: str | None) -> None:
    code, body = fetch(f"{api}/health")
    health = json.loads(body) if code == 200 else {}
    run.check("health 200", code == 200, f"HTTP {code}" if code else f"unreachable: {body.decode()[:120]}")
    run.check("version", health.get("version") == version, f"reported {health.get('version')!r}, expected {version!r}")
    if build:
        run.check("build sha", str(health.get("build", "")).startswith(build[:12]),
                  f"reported {health.get('build')!r}")
    code, body = fetch(f"{api}/ready")
    ready = json.loads(body) if body.startswith(b"{") else {}
    run.check("ready", code == 200 and ready.get("ready") is True, f"HTTP {code} {ready.get('checks')}")
    bundle = (ready.get("checks") or {}).get("detection_bundle", "")
    run.check("detection bundle published", bool(bundle) and bundle != "none published" and not str(bundle).startswith("error"),
              str(bundle))
    code, _ = fetch(f"{api}/v1/devices")
    run.check("protected route needs auth", code == 401, f"HTTP {code}")


def check_release(run: Run, tag: str, sample: int, all_assets: bool) -> None:
    code, body = fetch(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
    if not run.check("release exists", code == 200, f"{tag} HTTP {code}"):
        return
    assets = {a["name"]: a["browser_download_url"] for a in json.loads(body).get("assets", [])}
    if not run.check("SHA256SUMS.txt attached", "SHA256SUMS.txt" in assets):
        return
    _, sums_raw = fetch(assets["SHA256SUMS.txt"])
    sums = {}
    for line in sums_raw.decode().splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    missing = sorted(n for n in sums if n not in assets)
    run.check("every listed asset attached", not missing, ", ".join(missing) or f"{len(sums)} entries")
    run.check("no empty-file hashes", EMPTY_SHA256 not in sums.values())
    names = sorted(n for n in sums if n in assets and not n.endswith(".blockmap"))
    if not all_assets:
        names = sorted(names, key=lambda n: ("agent" not in n, n))[:sample]
    for n in names:
        code, data = fetch(assets[n], timeout=600)
        got = hashlib.sha256(data).hexdigest()
        run.check(f"sha256 {n}", code == 200 and got == sums[n], f"{len(data) / 1e6:.1f} MB")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--version", required=True)
    ap.add_argument("--build")
    ap.add_argument("--tag")
    ap.add_argument("--sample", type=int, default=4)
    ap.add_argument("--all-assets", action="store_true")
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--evidence")
    a = ap.parse_args()
    run = Run()
    if not a.skip_api:
        check_api(run, a.api.rstrip("/"), a.version, a.build)
    if a.tag:
        check_release(run, a.tag, a.sample, a.all_assets)
    record = {"tool": "tools/smoke_release.py", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "api": a.api, "version": a.version, "tag": a.tag, "build": a.build,
              "passed": run.passed, "checks": run.checks}
    if a.evidence:
        with open(a.evidence, "w") as f:
            json.dump(record, f, indent=1)
            f.write("\n")
    print("SMOKE PASSED" if run.passed else "SMOKE FAILED")
    return 0 if run.passed else 1


if __name__ == "__main__":
    sys.exit(main())
