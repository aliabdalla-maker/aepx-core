"""Local agent state: protected directory, offline event buffer, idempotency ledger, verified
policy and update history.

Trace: OPS-02 (enforce last verified policy offline; buffer within a configured size limit;
replay on reconnection; rollback to a verified version), EDR-02 (duplicate commands -> one
effective action), ARC-01 (protect agent configuration; report degraded protection).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import threading
import time
import uuid
from pathlib import Path


class State:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self.root, 0o700)
        (self.root / "quarantine").mkdir(exist_ok=True)
        (self.root / "updates").mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(self.root / "agent.db", check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT UNIQUE NOT NULL,
              kind TEXT NOT NULL, priority INTEGER NOT NULL, body TEXT NOT NULL, size INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS seen_commands (idempotency_key TEXT PRIMARY KEY, command_id TEXT NOT NULL,
              status TEXT NOT NULL, result TEXT NOT NULL, at REAL NOT NULL);
        """)

    # -------------------------------------------------------------- kv
    def get(self, k: str, default=None):
        row = self.db.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, k: str, v) -> None:
        with self._lock:
            self.db.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                            (k, json.dumps(v)))

    # -------------------------------------------------------------- events
    def buffer_limit_bytes(self) -> int:
        pol = self.get("policy") or {}
        return int(pol.get("bundle", {}).get("body", {}).get("event_buffer_mb", 64)) * 1024 * 1024

    def add_event(self, kind: str, data: dict, occurred_at: str | None = None) -> str:
        uid = uuid.uuid4().hex
        body = json.dumps({"event_uid": uid, "kind": kind, "data": data,
                           "occurred_at": occurred_at or time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())})
        priority = 2 if kind in ("detection", "quarantine", "tamper") else 1
        with self._lock:
            self.db.execute("INSERT INTO events (uid, kind, priority, body, size) VALUES (?,?,?,?,?)",
                            (uid, kind, priority, body, len(body)))
            self._enforce_limit()
        return uid

    def _enforce_limit(self) -> None:
        limit = self.buffer_limit_bytes()
        total = self.db.execute("SELECT COALESCE(sum(size), 0) FROM events").fetchone()[0]
        dropped = 0
        while total > limit:
            row = self.db.execute("SELECT seq, size FROM events ORDER BY priority ASC, seq ASC LIMIT 1").fetchone()
            if not row:
                break
            self.db.execute("DELETE FROM events WHERE seq = ?", (row[0],))
            total -= row[1]
            dropped += 1
        if dropped:
            self.db.execute("INSERT INTO kv (k, v) VALUES ('dropped_events', ?) ON CONFLICT(k) DO UPDATE SET "
                            "v = CAST(CAST(v AS INTEGER) + ? AS TEXT)", (str(dropped), dropped))

    def pending_events(self, limit: int = 1000) -> list[tuple[int, dict]]:
        rows = self.db.execute("SELECT seq, body FROM events ORDER BY seq LIMIT ?", (limit,)).fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def ack_events(self, seqs: list[int]) -> None:
        with self._lock:
            self.db.executemany("DELETE FROM events WHERE seq = ?", [(s,) for s in seqs])

    def buffered_bytes(self) -> int:
        return self.db.execute("SELECT COALESCE(sum(size), 0) FROM events").fetchone()[0]

    # -------------------------------------------------------------- idempotency
    def seen(self, key: str):
        row = self.db.execute("SELECT command_id, status, result FROM seen_commands WHERE idempotency_key = ?",
                              (key,)).fetchone()
        return {"command_id": row[0], "status": row[1], "result": json.loads(row[2])} if row else None

    def mark_seen(self, key: str, command_id: str, status: str, result: dict) -> None:
        with self._lock:
            self.db.execute("INSERT OR IGNORE INTO seen_commands VALUES (?,?,?,?,?)",
                            (key, command_id, status, json.dumps(result), time.time()))

    # -------------------------------------------------------------- tamper protection
    def config_fingerprint(self) -> str:
        h = hashlib.sha256()
        for name in ("identity.json",):
            p = self.root / name
            if p.exists():
                h.update(p.read_bytes())
        if os.name == "posix":
            h.update(str(stat.S_IMODE(os.stat(self.root).st_mode)).encode())
        return h.hexdigest()
