"""Offline SQLite replay ledger for signed authorization contexts.

Local single-host testing only. NOT a distributed PostgreSQL authorization
boundary, and does not prove the caller is authenticated. No external calls.
"""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from scripts.aepx_trusted_tenant_context import (
    AuthorizationDenied, verify_context, _canonical)

SCHEMA="""CREATE TABLE IF NOT EXISTS consumed_context(
 fingerprint TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL,
 principal_id TEXT NOT NULL,
 action TEXT NOT NULL,
 expires_at INTEGER NOT NULL,
 consumed_at INTEGER NOT NULL
)"""

def consume_once(database,claims,signature,key,tenant_id,principal_id,action,now=None):
    """Verify then atomically consume one context. Fails closed on replay.

    Never invoke a provider or mutate business state based on this local
    ledger; DB-side authorization must be atomic with the protected action.
    """
    clock=int(time.time()) if now is None else now
    verify_context(claims,signature,key,tenant_id,principal_id,action,now=clock)
    if not isinstance(database,(str,os.PathLike)) or not str(database):
        raise AuthorizationDenied("database path required")
    path=Path(database)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise AuthorizationDenied("unsafe ledger path")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise AuthorizationDenied("unsafe ledger directory")
    fingerprint=hashlib.sha256(_canonical(claims)+bytes.fromhex(signature)).hexdigest()
    try:
        with sqlite3.connect(str(path),timeout=5,isolation_level=None) as db:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("BEGIN IMMEDIATE")
            db.execute(SCHEMA)
            try:
                db.execute("INSERT INTO consumed_context VALUES(?,?,?,?,?,?)",
                           (fingerprint,tenant_id,principal_id,action,claims["expires_at"],clock))
            except sqlite3.IntegrityError as exc:
                db.execute("ROLLBACK")
                raise AuthorizationDenied("authorization replay") from exc
            db.execute("COMMIT")
    except sqlite3.Error as exc:
        raise AuthorizationDenied("authorization ledger unavailable") from exc
    return True
