"""Offline persistent budget reservation ledger. No provider calls or execution authority.

Single-host cooperative writers only. Never auto-release unknown in-flight reservations.
"""
import json
import os
import tempfile
from pathlib import Path
from aepx_pilot_checkpoint import exclusive_checkpoint_lock
from aepx_budget_admission import admit, BudgetDenied, _integer, _money

KEYS = ("tokens", "cost_usd", "seconds", "repair_attempts")
MAX_LEDGER_BYTES = 4 * 1024 * 1024
MAX_RESERVATIONS = 10000

def _valid_request_id(value):
    return (isinstance(value, str) and 1 <= len(value) <= 128 and
            all(c.isascii() and (c.isalnum() or c in "-_") for c in value))

def _validate_amounts(amounts):
    if not isinstance(amounts, dict) or set(amounts) != set(KEYS):
        raise BudgetDenied("invalid budget fields")
    for key in KEYS:
        (_money if key == "cost_usd" else _integer)(amounts[key], key)
    return amounts

def _zero():
    return {"tokens":0, "cost_usd":"0", "seconds":0, "repair_attempts":0}

def _add(a, b):
    result = {}
    for key in KEYS:
        result[key] = str(_money(a[key],key)+_money(b[key],key)) if key == "cost_usd" else a[key]+b[key]
    return result

def _read(path):
    if path.is_symlink():
        raise BudgetDenied("symlink ledger forbidden")
    if not path.exists():
        return {"schema_version":1,"reservations":{}}
    if not path.is_file():
        raise BudgetDenied("invalid ledger path")
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise BudgetDenied("ledger exceeds size limit")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state,dict) or set(state) != {"schema_version","reservations"} or state["schema_version"] != 1 or not isinstance(state["reservations"],dict):
        raise BudgetDenied("invalid ledger")
    if len(state["reservations"]) > MAX_RESERVATIONS:
        raise BudgetDenied("reservation count limit exceeded")
    for request_id, entry in state["reservations"].items():
        if not _valid_request_id(request_id):
            raise BudgetDenied("invalid persisted request id")
        if not isinstance(entry,dict) or set(entry) != {"reserved","settled"}:
            raise BudgetDenied("invalid reservation")
        _validate_amounts(entry["reserved"])
        if entry["settled"] is not None:
            _validate_amounts(entry["settled"])
            admit(entry["reserved"],_zero(),entry["settled"])
    return state

def _write(path, state):
    payload = json.dumps(state,sort_keys=True,indent=2) + "\\n"
    if len(payload.encode("utf-8")) > MAX_LEDGER_BYTES:
        raise BudgetDenied("ledger exceeds size limit")
    fd, temp = tempfile.mkstemp(prefix=".aepx-budget-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(state,stream,sort_keys=True,indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def _total(state):
    total = _zero()
    for entry in state["reservations"].values():
        total = _add(total, entry["settled"] if entry["settled"] is not None else entry["reserved"])
    return total

def reserve(path, request_id, limits, planned):
    """Atomically admit and reserve; retries with same ID and values are idempotent."""
    path = Path(path)
    if path.parent.is_symlink() or not path.parent.is_dir() or path.is_symlink():
        raise BudgetDenied("unsafe budget ledger path")
    if not _valid_request_id(request_id):
        raise BudgetDenied("invalid request id")
    _validate_amounts(limits)
    _validate_amounts(planned)
    with exclusive_checkpoint_lock(path):
        state = _read(path)
        existing = state["reservations"].get(request_id)
        if existing is not None:
            if existing["reserved"] != planned:
                raise BudgetDenied("conflicting request id")
            return {"request_id":request_id,"status":"already_reserved","external_execution_authorized":False}
        if len(state["reservations"]) >= MAX_RESERVATIONS:
            raise BudgetDenied("reservation count limit exceeded")
        admit(limits,_total(state),planned)
        state["reservations"][request_id] = {"reserved":planned,"settled":None}
        if len(json.dumps(state).encode("utf-8")) > MAX_LEDGER_BYTES:
            raise BudgetDenied("ledger exceeds size limit")
        _write(path,state)
        return {"request_id":request_id,"status":"reserved","external_execution_authorized":False}

def settle(path, request_id, actual):
    """Settle only within reserved maximum; never infer a release on crash."""
    path = Path(path)
    _validate_amounts(actual)
    if path.parent.is_symlink() or path.is_symlink():
        raise BudgetDenied("unsafe budget ledger path")
    with exclusive_checkpoint_lock(path):
        state = _read(path)
        entry = state["reservations"].get(request_id)
        if entry is None:
            raise BudgetDenied("unknown request")
        admit(entry["reserved"],_zero(),actual)
        if entry["settled"] is not None:
            if entry["settled"] != actual:
                raise BudgetDenied("conflicting settlement")
            return {"request_id":request_id,"status":"already_settled"}
        entry["settled"] = actual
        _write(path,state)
        return {"request_id":request_id,"status":"settled"}
