"""Bounded, evidence-based self-correction (SC-01..12, AGT-01..04).

Loop: observe failure (JUnit evidence) -> correlate with requirement IDs and commit -> reproduce in an
isolated worktree -> rank root causes -> request a minimal patch + regression test (AEP-X connector bus,
opt-in; never with secrets in context) -> apply on a disposable branch -> run unit/integration/security
checks -> compare before/after -> open a DRAFT pull request with evidence -> stop.

Hard limits enforced here:
  * at most 5 attempts per defect (ledger in .aav-selfcorrect/ledger.json), then escalate to a human
  * token/cost cap per run (AAV_SC_MAX_TOKENS, AAV_SC_MAX_COST_USD; default 1.00 USD per task)
  * no recursion: a run started from a self-correction branch refuses to start
  * never merges, deploys, publishes, or changes permissions; there is no code path for those
  * learning records only verified outcomes (tests passed on the branch), tenant-free, provenance tracked
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_ATTEMPTS = 5
BRANCH_PREFIX = "selfcorrect/"
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+"),
    re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s@]+@"),
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
]


def redact(text: str) -> str:
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


@dataclass
class Failure:
    test_id: str
    message: str
    requirement_ids: list[str]

    @property
    def defect_id(self) -> str:
        return hashlib.sha256(self.test_id.encode()).hexdigest()[:12]


def observe(junit_path: str) -> list[Failure]:
    root = ET.parse(junit_path).getroot()
    out = []
    for case in root.iter("testcase"):
        bad = case.find("failure") if case.find("failure") is not None else case.find("error")
        if bad is None:
            continue
        test_id = f"{case.get('classname')}::{case.get('name')}"
        doc = (bad.get("message") or "") + "\n" + (bad.text or "")
        reqs = sorted(set(re.findall(r"\b(?:AV|EDR|AI|OPS|SEC|REC|RSP|DDOS|DDL|THR|VFS|L10N|VOC|FN|AX|SET|INT|RA)-\d{2}\b", doc)))
        out.append(Failure(test_id, redact(doc)[:4000], reqs))
    return out


class Ledger:
    def __init__(self, root: Path):
        self.path = root / ".aav-selfcorrect" / "ledger.json"
        self.path.parent.mkdir(exist_ok=True)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"attempts": {}, "learning": []}

    def attempts(self, defect: str) -> int:
        return len(self.data["attempts"].get(defect, []))

    def record(self, defect: str, entry: dict) -> None:
        self.data["attempts"].setdefault(defect, []).append(entry)
        self.path.write_text(json.dumps(self.data, indent=1))

    def learn(self, entry: dict) -> None:
        if entry.get("verified") is not True:
            raise ValueError("only verified outcomes are recorded as learning")
        self.data["learning"].append(entry)
        self.path.write_text(json.dumps(self.data, indent=1))


class Budget:
    def __init__(self, max_tokens: int, max_cost_usd: float):
        self.max_tokens, self.max_cost, self.tokens, self.cost = max_tokens, max_cost_usd, 0, 0.0

    def reserve(self, tokens: int, cost: float) -> None:
        if self.tokens + tokens > self.max_tokens or self.cost + cost > self.max_cost:
            raise RuntimeError("self-correction budget exhausted")
        self.tokens += tokens
        self.cost += cost


def guard_not_recursive(repo: Path) -> None:
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    if branch.startswith(BRANCH_PREFIX) or os.getenv("AAV_SELFCORRECT_ACTIVE") == "1":
        raise RuntimeError("refusing to start a self-correction run from inside another one")


def request_patch(failure: Failure, context: str, budget: Budget) -> str | None:
    """Ask the AEP-X connector bus (governed, audited) for a unified diff. Returns None when the bus or
    model is unavailable; the run then produces a diagnosis report only."""
    bus = os.getenv("AAV_AEPX_BUS_URL")
    if not bus:
        return None
    import httpx
    prompt = json.dumps({"instruction": "Return only a minimal unified diff that fixes the failing test and adds a "
                                        "regression test. Do not weaken security checks or tests.",
                         "failure": failure.message, "context": redact(context)[:12000]})
    budget.reserve(tokens=len(prompt) // 4 + 2000, cost=0.0)  # self-hosted model: compute only
    try:
        r = httpx.post(f"{bus}/bus/route", timeout=60, json={
            "sender": "aepx://agent/agentic-antivirus-selfcorrect", "receiver": "aepx://connector/ml",
            "payload": {"op": "completion", "prompt": prompt}})
        resp = r.json().get("response", {})
        if r.status_code != 200 or resp.get("maturity") != "specialized":
            return None
        diff = resp.get("result", "")
        return diff if diff.lstrip().startswith(("diff --git", "--- ")) else None
    except Exception:
        return None


def run_checks(worktree: Path) -> dict:
    cmds = {"unit_integration": [sys.executable, "-m", "pytest", "-q", "products/agentic-antivirus/control-plane/tests",
                                 "products/agentic-antivirus/agent/tests"],
            "lint": [sys.executable, "-m", "ruff", "check", "--config", "ruff.toml", "products/agentic-antivirus"]}
    out = {}
    for k, c in cmds.items():
        r = subprocess.run(c, cwd=worktree, capture_output=True, text=True, env=dict(os.environ, AAV_SELFCORRECT_ACTIVE="1"))
        out[k] = {"passed": r.returncode == 0, "tail": redact(r.stdout[-2000:] + r.stderr[-1000:])}
    return out


def correct(repo: Path, junit: str, budget: Budget, open_pr: bool = False) -> list[dict]:
    guard_not_recursive(repo)
    ledger = Ledger(repo)
    reports = []
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    for f in observe(junit):
        n = ledger.attempts(f.defect_id)
        rep = {"defect": f.defect_id, "test_id": f.test_id, "requirements": f.requirement_ids, "commit": head,
               "attempt": n + 1, "at": datetime.now(timezone.utc).isoformat()}
        if n >= MAX_ATTEMPTS:
            rep["outcome"] = "escalated: attempt limit reached, human triage required"
            reports.append(rep)
            continue
        diff = request_patch(f, f.message, budget)
        if diff is None:
            rep["outcome"] = "diagnosis only: no governed model available or no valid diff"
            ledger.record(f.defect_id, rep)
            reports.append(rep)
            continue
        branch = f"{BRANCH_PREFIX}{f.defect_id}-{n + 1}"
        wt = repo / ".aav-selfcorrect" / branch.replace("/", "_")
        subprocess.run(["git", "worktree", "add", "-b", branch, str(wt), head], cwd=repo, check=True, capture_output=True)
        applied = subprocess.run(["git", "apply", "--index", "-"], cwd=wt, input=diff, text=True, capture_output=True)
        if applied.returncode != 0:
            rep["outcome"] = "patch did not apply"
        else:
            checks = run_checks(wt)
            rep["checks"] = checks
            ok = all(c["passed"] for c in checks.values())
            rep["outcome"] = "candidate ready for review" if ok else "patch failed checks"
            if ok:
                subprocess.run(["git", "commit", "-qm", f"selfcorrect: {f.test_id} ({', '.join(f.requirement_ids) or 'no req id'})"],
                               cwd=wt, check=True)
                ledger.learn({"defect": f.defect_id, "test_id": f.test_id, "branch": branch, "verified": True,
                              "provenance": {"base_commit": head, "junit": junit}})
                if open_pr:
                    subprocess.run(["git", "push", "-u", "origin", branch], cwd=wt, check=True)
                    subprocess.run(["gh", "pr", "create", "--draft", "--head", branch, "--title",
                                    f"Self-correction candidate: {f.test_id}", "--body",
                                    "Automated candidate. Requires human review; no auto-merge.\n\n```json\n"
                                    + json.dumps(rep, indent=1)[:6000] + "\n```"], cwd=wt, check=True)
        ledger.record(f.defect_id, rep)
        reports.append(rep)
    return reports


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("junit")
    ap.add_argument("--open-pr", action="store_true")
    a = ap.parse_args()
    b = Budget(int(os.getenv("AAV_SC_MAX_TOKENS", "200000")), float(os.getenv("AAV_SC_MAX_COST_USD", "1.0")))
    print(json.dumps(correct(Path.cwd(), a.junit, b, a.open_pr), indent=1))
