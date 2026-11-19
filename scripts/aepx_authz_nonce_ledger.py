"""Offline SQLite replay ledger for signed authorization contexts.

Local single-host testing only. Schema change requires a fresh disposable ledger. NOT a distributed PostgreSQL authorization
boundary, and does not prove the caller is authenticated. No external calls.
"""
import hashlib
from contextlib import closing
import os
import sqlite3
import time
from pathlib import Path
from scripts.aepx_trusted_tenant_context import (
    AuthorizationDenied, verify_context, _canonical)

SCHEMA="""CREATE TABLE IF NOT EXISTS consumed_context(
 fingerprint TEXT PRIMARY KEY,
 nonce TEXT NOT NULL,
 tenant_id TEXT NOT NULL,
 principal_id TEXT NOT NULL,
 action TEXT NOT NULL,
 expires_at INTEGER NOT NULL,
 consumed_at INTEGER NOT NULL,
 UNIQUE(tenant_id,principal_id,action,nonce)
)"""

EXPECTED_COLUMNS=("fingerprint","nonce","tenant_id","principal_id","action","expires_at","consumed_at")

def _assert_current_schema(db):
    """Reject legacy or modified schemas before any authorization insert."""
    columns=db.execute("PRAGMA table_info(consumed_context)").fetchall()
    if tuple(column[1] for column in columns)!=EXPECTED_COLUMNS:
        raise AuthorizationDenied("incompatible authorization ledger schema")
    indexes=db.execute("PRAGMA index_list(consumed_context)").fetchall()
    unique_sets=set()
    for index in indexes:
        if index[2]:
            cols=db.execute('PRAGMA index_info("'+index[1].replace('"','""')+'")').fetchall()
            unique_sets.add(tuple(col[2] for col in cols))
    if ("tenant_id","principal_id","action","nonce") not in unique_sets:
        raise AuthorizationDenied("nonce uniqueness constraint missing")

def consume_once(database,claims,signature,key,tenant_id,principal_id,action,now=None):
    """Verify then atomically consume one context. Fails closed on replay.

    Never invoke a provider or mutate business state based on this local
    ledger; DB-side authorization must be atomic with the protected action.
    """
    clock=int(time.time()) if now is None else now
    if type(clock) is not int:
        raise AuthorizationDenied('invalid clock')
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
        with closing(sqlite3.connect(str(path),timeout=5,isolation_level=None)) as db:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(SCHEMA)
                _assert_current_schema(db)
                db.execute("INSERT INTO consumed_context VALUES(?,?,?,?,?,?,?)",
                           (fingerprint,claims["nonce"],tenant_id,principal_id,action,claims["expires_at"],clock))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
    except sqlite3.IntegrityError as exc:
        raise AuthorizationDenied("authorization replay or invalid ledger schema") from exc
    except sqlite3.Error as exc:
        raise AuthorizationDenied("authorization ledger unavailable") from exc
    return True
