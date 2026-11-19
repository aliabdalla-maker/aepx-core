"""Loads the latest published, signed detection bundle into the shared engine (ARC-03, VFS-12)."""
from __future__ import annotations

import threading

from aav_detection import Engine, validate_bundle  # noqa: F401  (re-exported for routers)

from app import db

_lock = threading.Lock()
_cache: dict = {"version": None, "engine": None}


def current_engine() -> Engine | None:
    with db.global_tx() as cur:
        cur.execute("SELECT version, body FROM aav.update_bundles WHERE kind = 'detections' AND revoked_at IS NULL "
                    "ORDER BY published_at DESC LIMIT 1")
        row = cur.fetchone()
    if not row:
        return None
    with _lock:
        if _cache["version"] != row["version"]:
            _cache["engine"] = Engine(row["body"], row["version"])
            _cache["version"] = row["version"]
        return _cache["engine"]
