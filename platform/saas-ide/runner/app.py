"""AEP-X sandbox runner: an internal HTTP service that runs project code with sandbox.run().

Only the IDE API may call it. Every request is signed with HMAC-SHA256 over
"<timestamp>.<body>" using RUNNER_SHARED_SECRET; requests older than 60 s or replayed are
refused. At most RUNNER_MAX_CONCURRENT runs execute at once; extra requests get 429.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request

import sandbox

app = FastAPI(title="AEP-X sandbox runner", docs_url=None, redoc_url=None, openapi_url=None)
_slots = threading.BoundedSemaphore(max(1, min(int(os.getenv("RUNNER_MAX_CONCURRENT", "2") or 2), 16)))
_seen: "OrderedDict[str, float]" = OrderedDict()
_seen_lock = threading.Lock()
WINDOW = 60


def _secret() -> bytes:
    s = os.getenv("RUNNER_SHARED_SECRET", "")
    if len(s) < 32:
        raise HTTPException(503, "Runner is not configured")
    return s.encode()


def sign(secret: bytes, timestamp: str, body: bytes) -> str:
    return hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(headers, body: bytes, now: float | None = None) -> None:
    ts, sig = headers.get("x-aepx-timestamp", ""), headers.get("x-aepx-signature", "")
    now = time.time() if now is None else now
    if not ts.isdigit() or abs(now - int(ts)) > WINDOW or len(sig) != 64:
        raise HTTPException(401, "Unsigned or expired request")
    if not hmac.compare_digest(sign(_secret(), ts, body), sig):
        raise HTTPException(401, "Bad signature")
    with _seen_lock:
        while _seen and next(iter(_seen.values())) < now - WINDOW:
            _seen.popitem(last=False)
        if sig in _seen:
            raise HTTPException(409, "Replayed request")
        _seen[sig] = now


@app.get("/health")
def health():
    return {"status": "ok", "runtime": os.getenv("RUNNER_RUNTIME", "runsc"),
            "languages": sorted(sandbox.LANGUAGES)}


@app.post("/run")
async def run(request: Request):
    body = await request.body()
    if len(body) > 3_000_000:
        raise HTTPException(413, "Request too large")
    verify(request.headers, body)
    try:
        req = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, "The runner is busy; try again in a moment")
    try:
        result = sandbox.run(req.get("files"), req.get("entry", ""), language=req.get("language"),
                             stdin=req.get("stdin", "") or "")
    except sandbox.SandboxError as exc:
        raise HTTPException(400, str(exc))
    finally:
        _slots.release()
    return {k: v for k, v in result.__dict__.items() if k != "extra"}
