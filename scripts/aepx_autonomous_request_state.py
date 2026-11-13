"""Offline durable request lifecycle for a supervised AEP-X runner.

No network, subprocess, OpenAI API, GitHub or deployment operations.
"""
import sqlite3
from pathlib import Path

class StateDenied(ValueError):
    pass

STATES = ("planned", "reserved", "dispatched", "uncertain", "settled", "failed")
TRANSITIONS = {
    "planned": frozenset({"reserved", "failed"}),
    "reserved": frozenset({"dispatched", "failed", "uncertain"}),
    "dispatched": frozenset({"uncertain", "settled"}),
    "uncertain": frozenset({"settled", "failed"}),
    "settled": frozenset(),
    "failed": frozenset(),
}

def connect(path):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise StateDenied("invalid state database path")
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        request_id TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK(state IN ('planned','reserved','dispatched','uncertain','settled','failed')),
        attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 3),
        evidence TEXT NOT NULL DEFAULT '',
        revision INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS request_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        from_state TEXT NOT NULL,
        to_state TEXT NOT NULL,
        revision INTEGER NOT NULL,
        evidence TEXT NOT NULL,
        UNIQUE(request_id,revision))""")
    return conn

def valid_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 256 and all(
        c.isalnum() or c in "-_:." for c in value)

def create(conn, request_id):
    if not valid_id(request_id):
        raise StateDenied("invalid request identifier")
    conn.execute("INSERT INTO requests(request_id,state) VALUES(?,'planned')",(request_id,))

def transition(conn, request_id, expected, target, *, evidence, increment_attempt=False):
    if expected not in TRANSITIONS or target not in TRANSITIONS[expected]:
        raise StateDenied("invalid state transition")
    if not isinstance(evidence,str) or not 1 <= len(evidence) <= 2000:
        raise StateDenied("evidence required")
    if type(increment_attempt) is not bool:
        raise StateDenied("invalid attempt increment")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT state,attempt,revision FROM requests WHERE request_id=?",
                           (request_id,)).fetchone()
        if row is None or row[0] != expected:
            raise StateDenied("stale or unknown request state")
        attempt = row[1] + int(increment_attempt)
        if attempt > 3:
            raise StateDenied("repair attempt limit reached")
        revision = row[2] + 1
        conn.execute("""UPDATE requests SET state=?,attempt=?,evidence=?,revision=?
                        WHERE request_id=?""",(target,attempt,evidence,revision,request_id))
        conn.execute("""INSERT INTO request_events(request_id,from_state,to_state,revision,evidence)
                        VALUES(?,?,?,?,?)""",(request_id,expected,target,revision,evidence))
        conn.execute("COMMIT")
        return {"request_id":request_id,"state":target,"attempt":attempt,"revision":revision}
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def recover_dispatched(conn):
    """Fail closed: ambiguous dispatches become uncertain, never reissued."""
    rows = conn.execute("SELECT request_id FROM requests WHERE state='dispatched'").fetchall()
    for (request_id,) in rows:
        transition(conn,request_id,"dispatched","uncertain",
                   evidence="recovery: dispatch outcome unknown; manual reconciliation required")
    return len(rows)

def snapshot(conn):
    return conn.execute("SELECT request_id,state,attempt,revision FROM requests ORDER BY request_id").fetchall()
