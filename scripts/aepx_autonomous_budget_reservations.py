"""SQLite transactional reservation ledger for a single-host autonomous runner.

Offline component. Callers must obtain trustworthy provider receipts and prices.
Do not use across networked hosts or as a substitute for provider billing limits.
"""
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_SQLITE_INTEGER = 2**63 - 1

class BudgetDenied(ValueError):
    pass

SCALE = 1_000_000_000  # integer nanodollars

def units(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise BudgetDenied("use exact decimal strings")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise BudgetDenied("invalid amount") from exc
    if not amount.is_finite() or amount < 0 or amount * SCALE != (amount * SCALE).to_integral_value():
        raise BudgetDenied("invalid precision or negative/nonfinite amount")
    result = int(amount * SCALE)
    if result > MAX_SQLITE_INTEGER:
        raise BudgetDenied("amount exceeds SQLite integer range")
    return result

def connect(path):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise BudgetDenied("invalid database path")
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS budget(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        cap INTEGER NOT NULL CHECK(cap>0),
        spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reservations(
        request_id TEXT PRIMARY KEY,
        reserved INTEGER NOT NULL CHECK(reserved>0),
        charged INTEGER,
        status TEXT NOT NULL CHECK(status IN ('reserved','settled','uncertain')),
        CHECK(charged IS NULL OR (charged>=0 AND charged<=reserved)))""")
    return conn

def initialize(conn, cap_usd):
    cap = units(cap_usd)
    if cap <= 0:
        raise BudgetDenied("positive cap required")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT cap FROM budget WHERE singleton=1").fetchone()
        if row is None:
            conn.execute("INSERT INTO budget(singleton,cap,spent) VALUES(1,?,0)",(cap,))
        elif cap > row[0]:
            raise BudgetDenied("budget cap escalation denied")
        else:
            spent = conn.execute("SELECT spent FROM budget WHERE singleton=1").fetchone()[0]
            held = conn.execute("SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE status IN ('reserved','uncertain')").fetchone()[0]
            if cap <= spent + held:
                raise BudgetDenied("new cap cannot invalidate existing spending and holds")
            conn.execute("UPDATE budget SET cap=? WHERE singleton=1",(cap,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def reserve(conn, request_id, amount_usd):
    amount = units(amount_usd)
    if not isinstance(request_id,str) or not 1 <= len(request_id) <= 256 or amount <= 0:
        raise BudgetDenied("invalid reservation")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT cap,spent FROM budget WHERE singleton=1").fetchone()
        if row is None:
            raise BudgetDenied("budget not initialized")
        held = conn.execute("SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE status IN ('reserved','uncertain')").fetchone()[0]
        if row[1] + held + amount >= row[0]:
            raise BudgetDenied("insufficient available budget")
        conn.execute("INSERT INTO reservations(request_id,reserved,status) VALUES(?,?,'reserved')",(request_id,amount))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def settle(conn, request_id, charge_usd):
    charge = units(charge_usd)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT reserved,status FROM reservations WHERE request_id=?",(request_id,)).fetchone()
        if row is None or row[1] != "reserved" or charge > row[0]:
            raise BudgetDenied("missing, uncertain, duplicate or over-reservation settlement")
        conn.execute("UPDATE reservations SET charged=?,status='settled' WHERE request_id=?",(charge,request_id))
        conn.execute("UPDATE budget SET spent=spent+? WHERE singleton=1",(charge,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def mark_uncertain(conn, request_id):
    """Retain full reserved funds after an ambiguous provider response."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT status FROM reservations WHERE request_id=?",(request_id,)).fetchone()
        if row is None or row[0] != "reserved":
            raise BudgetDenied("cannot mark missing or finalized reservation uncertain")
        conn.execute("UPDATE reservations SET status='uncertain' WHERE request_id=?",(request_id,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise

def snapshot(conn):
    budget = conn.execute("SELECT cap,spent FROM budget WHERE singleton=1").fetchone()
    if budget is None:
        raise BudgetDenied("budget not initialized")
    held = conn.execute("SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE status IN ('reserved','uncertain')").fetchone()[0]
    return {"cap_usd":str(Decimal(budget[0])/SCALE),
            "spent_usd":str(Decimal(budget[1])/SCALE),
            "held_usd":str(Decimal(held)/SCALE),
            "available_usd":str(Decimal(budget[0]-budget[1]-held)/SCALE)}

def reconcile_uncertain(conn, request_id, charge_usd, *, receipt_id, verified=False):
    """Settle an ambiguous request only after independent billing verification.

    A distinct receipt identifier is unique across reconciliations; callers
    must independently verify receipt authenticity and amount.
    """
    if verified is not True:
        raise BudgetDenied("independent billing verification required")
    if not isinstance(receipt_id, str) or not 1 <= len(receipt_id) <= 256:
        raise BudgetDenied("valid external receipt id required")
    charge = units(charge_usd)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS reconciliation_receipts(
            receipt_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
            charge INTEGER NOT NULL CHECK(charge>=0))""")
        row = conn.execute("SELECT reserved,status FROM reservations WHERE request_id=?",
                           (request_id,)).fetchone()
        if row is None or row[1] != "uncertain" or charge > row[0]:
            raise BudgetDenied("only uncertain reservations within cap can reconcile")
        conn.execute("INSERT INTO reconciliation_receipts(receipt_id,request_id,charge) VALUES(?,?,?)",
                     (receipt_id,request_id,charge))
        conn.execute("UPDATE reservations SET charged=?,status='settled' WHERE request_id=?",
                     (charge,request_id))
        conn.execute("UPDATE budget SET spent=spent+? WHERE singleton=1",(charge,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
