"""Run project code in the isolated sandbox runner.

The API never executes user code itself. It checks the caller's role, loads the project's files
from the tenant-scoped database, and sends them to the runner (a separate service on a
gVisor-isolated host) over an HMAC-signed request. Off unless IDE_CODE_EXECUTION_ENABLED=true and
the runner is configured; the UI shows the reason when it is off.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import acl
from .main import Principal, WorkspaceFile, db_session, principal, project_or_404, safe_path

router = APIRouter()
RUNNABLE = {".py": "python", ".js": "node", ".mjs": "node", ".cjs": "node"}
_recent: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


class RunIn(BaseModel):
    entry: str = Field(min_length=1, max_length=255)
    stdin: str = Field(default="", max_length=64_000)


def runner_url_ok(url: str) -> bool:
    """HTTPS anywhere; plain HTTP only to the same-host compose service or, when explicitly
    allowed, to a private-network address (OCI VCN), because the request carries user code."""
    from ipaddress import ip_address, ip_network
    from urllib.parse import urlparse
    # RFC 1918 and IPv6 unique-local only (ipaddress.is_private also accepts documentation ranges).
    private = [ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fd00::/8")]
    u = urlparse(url)
    if u.scheme == "https" and u.hostname:
        return True
    if u.scheme != "http" or not u.hostname:
        return False
    if u.hostname == "ide-runner":
        return True
    try:
        address = ip_address(u.hostname)
        return os.getenv("IDE_RUNNER_ALLOW_PRIVATE_HTTP") == "true" and any(
            address.version == n.version and address in n for n in private)
    except ValueError:
        return False


def status() -> dict:
    """Whether Run is available, and why not when it is not."""
    if os.getenv("IDE_CODE_EXECUTION_ENABLED") != "true":
        return {"enabled": False, "languages": [], "reason": "Running code is not switched on for this workspace yet."}
    if not runner_url_ok(os.getenv("IDE_RUNNER_URL", "")) or len(os.getenv("IDE_RUNNER_SECRET", "")) < 32:
        return {"enabled": False, "languages": [], "reason": "The code runner is not configured."}
    return {"enabled": True, "languages": ["python", "node"], "reason": ""}


def language_of(entry: str) -> str:
    for ext, lang in RUNNABLE.items():
        if entry.lower().endswith(ext):
            return lang
    raise HTTPException(400, "Only Python (.py) and JavaScript (.js, .mjs, .cjs) files can be run")


def rate_limited(subject: str, now: float | None = None) -> bool:
    limit = max(1, min(int(os.getenv("IDE_RUN_PER_MINUTE", "20") or 20), 600))
    now = time.monotonic() if now is None else now
    with _lock:
        q = _recent[subject]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def call_runner(payload: dict, client=None) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-AEPX-Timestamp": ts,
               "X-AEPX-Signature": sign(os.environ["IDE_RUNNER_SECRET"], ts, body)}
    url = os.environ["IDE_RUNNER_URL"].rstrip("/") + "/run"
    try:
        if client is None:
            import httpx
            with httpx.Client(timeout=75) as http:
                r = http.post(url, content=body, headers=headers)
        else:
            r = client.post(url, content=body, headers=headers)
    except Exception:
        raise HTTPException(503, "The code runner is unreachable right now. Try again shortly.")
    if r.status_code == 200:
        return r.json()
    if r.status_code in (400, 413):
        detail = None
        if r.headers.get("content-type", "").startswith("application/json"):
            detail = r.json().get("detail")
        raise HTTPException(400, detail or "The runner rejected this request")
    if r.status_code == 429:
        raise HTTPException(429, "The code runner is busy; try again in a moment.")
    raise HTTPException(503, "The code runner is unavailable right now.")


def load_files(db: Session, tenant: str, project_id: str) -> list[dict]:
    rows = db.scalars(select(WorkspaceFile).where(WorkspaceFile.tenant_id == tenant,
                                                  WorkspaceFile.project_id == project_id)).all()
    return [{"path": f.path, "content": f.content} for f in rows]


@router.get("/api/v1/execution")
def execution_status(p: Principal = Depends(principal)):
    s = status()
    if s["enabled"] and not acl.allowed(p.role, "execute_agent"):
        return {"enabled": False, "languages": [], "reason": "Your role cannot run code."}
    return s


@router.post("/api/v1/projects/{project_id}/run")
def run_code(project_id: str, body: RunIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    s = status()
    if not s["enabled"]:
        raise HTTPException(503, s["reason"])
    if not acl.allowed(p.role, "execute_agent"):
        raise HTTPException(403, "Your role cannot run code")
    entry = safe_path(body.entry)
    language = language_of(entry)
    project_or_404(db, p.tenant_id, project_id)
    files = load_files(db, p.tenant_id, project_id)
    if not any(f["path"] == entry for f in files):
        raise HTTPException(404, "Save the file before running it")
    if rate_limited(p.subject):
        raise HTTPException(429, "Too many runs; wait a minute and try again.")
    result = call_runner({"entry": entry, "language": language, "stdin": body.stdin, "files": files})
    from .universal import _commit, audit
    audit(db, p, "code.run", "file", f"{project_id}/{entry}",
          f"exit {result.get('exit_code')} in {result.get('duration_ms')} ms"
          + (" (timed out)" if result.get("timed_out") else ""))
    _commit(db)
    return {k: result.get(k) for k in ("stdout", "stderr", "exit_code", "timed_out", "duration_ms",
                                       "truncated", "runtime", "language")}
