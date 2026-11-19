#!/usr/bin/env python3
"""Local-only durable HITL state machine, backed by SQLite.
Not a production authorisation service. Caller identity MUST be authenticated upstream.
"""
import hashlib
import json
import sqlite3
import time
import uuid

class ApprovalDenied(PermissionError): pass

def action_hash(action):
    return hashlib.sha256(json.dumps(action,sort_keys=True,separators=(",",":")).encode()).hexdigest()

class ApprovalStore:
    def __init__(self,path):
        self.path=str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS approvals(
                id TEXT PRIMARY KEY, action_hash TEXT NOT NULL, requester TEXT NOT NULL,
                approver TEXT, status TEXT NOT NULL, expires_at REAL NOT NULL,
                created_at REAL NOT NULL, consumed_at REAL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT NOT NULL,
                event TEXT NOT NULL, actor TEXT NOT NULL, at REAL NOT NULL)""")
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        db.execute("PRAGMA busy_timeout=10000")
        return db
    def _event(self,db,approval_id,event,actor,now):
        db.execute("INSERT INTO events(approval_id,event,actor,at) VALUES(?,?,?,?)",
                   (approval_id,event,actor,now))
    def request(self,action,requester,ttl_seconds=900,now=None):
        if not requester or not isinstance(action,dict) or not action:
            raise ValueError("requester and action required")
        if ttl_seconds<=0 or ttl_seconds>86400:raise ValueError("invalid approval TTL")
        now=time.time() if now is None else now
        approval_id=str(uuid.uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO approvals(id,action_hash,requester,status,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                       (approval_id,action_hash(action),requester,"pending",now+ttl_seconds,now))
            self._event(db,approval_id,"requested",requester,now)
            db.commit()
        return approval_id
    def decide(self,approval_id,approver,allow,now=None):
        if not approver:raise ApprovalDenied("authenticated approver required")
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT requester,status,expires_at FROM approvals WHERE id=?",(approval_id,)).fetchone()
            if not row or row[1]!="pending" or now>=row[2] or row[0]==approver:
                db.rollback()
                raise ApprovalDenied("not pending, expired or self-approval prohibited")
            status="approved" if allow else "rejected"
            db.execute("UPDATE approvals SET status=?,approver=? WHERE id=?",(status,approver,approval_id))
            self._event(db,approval_id,status,approver,now)
            db.commit()
    def consume(self,approval_id,action,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT action_hash,status,expires_at,approver FROM approvals WHERE id=?",(approval_id,)).fetchone()
            if not row or row[1]!="approved" or row[0]!=action_hash(action) or now>=row[2]:
                db.rollback()
                raise ApprovalDenied("missing, expired, consumed or mismatched approval")
            changed=db.execute("UPDATE approvals SET status='consumed',consumed_at=? WHERE id=? AND status='approved'",
                               (now,approval_id)).rowcount
            if changed!=1:
                db.rollback()
                raise ApprovalDenied("approval already consumed")
            self._event(db,approval_id,"consumed",row[3],now)
            db.commit()
            return True
    def events(self,approval_id):
        with self.connect() as db:
            return db.execute("SELECT event,actor,at FROM events WHERE approval_id=? ORDER BY seq",
                              (approval_id,)).fetchall()
