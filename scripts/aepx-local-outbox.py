#!/usr/bin/env python3
"""Durable local outbox prototype: no network delivery or side effects."""
import json
import sqlite3
import time
import uuid

class Outbox:
    def __init__(self,path):
        self.path=str(path)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS outbox(
                id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                topic TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
                delivered_at REAL)""")
    def _db(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        db.execute("PRAGMA busy_timeout=10000")
        return db
    def enqueue(self,topic,payload,idempotency_key):
        if not topic or not idempotency_key or not isinstance(payload,dict):
            raise ValueError("topic, payload and idempotency key required")
        event_id=str(uuid.uuid4())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO outbox(id,idempotency_key,topic,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                       (event_id,idempotency_key,topic,json.dumps(payload,sort_keys=True),"pending",time.time()))
            result=db.execute("SELECT id FROM outbox WHERE idempotency_key=?",(idempotency_key,)).fetchone()[0]
            db.commit()
        return result
    def pending(self,limit=100):
        if limit<1 or limit>1000:raise ValueError("invalid limit")
        with self._db() as db:
            return db.execute("SELECT id,topic,payload FROM outbox WHERE status='pending' ORDER BY created_at,id LIMIT ?",(limit,)).fetchall()
    def mark_delivered(self,event_id):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("UPDATE outbox SET status='delivered',delivered_at=?,attempts=attempts+1 WHERE id=? AND status='pending'",
                               (time.time(),event_id)).rowcount
            db.commit()
        return changed==1
