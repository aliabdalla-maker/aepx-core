"""Offline, atomic-replacement engineering iteration state transitions.

No LLM, shell, network, code edits, merge, deployment or cloud access.
This is a local planning ledger, NOT an autonomous executor.
"""
import json
import os
import tempfile
from pathlib import Path

MAX_ITERATIONS = 10000
STAGES = ("requirements", "design", "patch_proposed", "tests_recorded", "reviewed", "completed")
NEXT = {a: b for a, b in zip(STAGES, STAGES[1:])}
MAX_BYTES = 4 * 1024 * 1024

class TransitionDenied(ValueError):
    pass

def validate(state):
    if not isinstance(state, dict) or state.get("version") != 1:
        raise TransitionDenied("invalid state version")
    items = state.get("iterations")
    if not isinstance(items, list) or len(items) > MAX_ITERATIONS:
        raise TransitionDenied("invalid iteration count")
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != {"number", "stage", "evidence"}:
            raise TransitionDenied("invalid iteration shape")
        if type(item["number"]) is not int or item["number"] != number or item["stage"] not in STAGES:
            raise TransitionDenied("invalid iteration sequence")
        evidence = item["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != set(STAGES[:STAGES.index(item["stage"])+1]):
            raise TransitionDenied("missing or extra stage evidence")
        for value in evidence.values():
            if not isinstance(value, str) or not 1 <= len(value) <= 256:
                raise TransitionDenied("invalid evidence reference")
    if any(item["stage"] != "completed" for item in items[:-1]):
        raise TransitionDenied("cannot begin another iteration before completion")
    return state

def load(path):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "iterations": []}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise TransitionDenied("unsafe or oversized ledger")
    return validate(json.loads(path.read_text(encoding="utf-8")))

def advance(state, *, number, stage, evidence):
    validate(state)
    if not isinstance(evidence, str) or not 1 <= len(evidence) <= 256:
        raise TransitionDenied("evidence reference required")
    items = state["iterations"]
    if type(number) is not int or number < 1 or number > MAX_ITERATIONS:
        raise TransitionDenied("invalid iteration number")
    if number == len(items) + 1 and stage == "requirements" and (not items or items[-1]["stage"] == "completed"):
        next_items = items + [{"number": number, "stage": stage, "evidence": {stage: evidence}}]
    elif number == len(items) and items:
        last = items[-1]
        if NEXT.get(last["stage"]) != stage:
            raise TransitionDenied("out-of-order or duplicate transition")
        next_items = items[:-1] + [{**last, "stage": stage, "evidence": {**last["evidence"], stage: evidence}}]
    else:
        raise TransitionDenied("invalid iteration transition")
    candidate = {"version": 1, "iterations": next_items}
    validate(candidate)
    if len(json.dumps(candidate, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise TransitionDenied("ledger size limit")
    return candidate

def persist(path, state):
    validate(state)
    path = Path(path)
    if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
        raise TransitionDenied("unsafe ledger path")
    payload = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise TransitionDenied("ledger size limit")
    fd, tmp = tempfile.mkstemp(prefix=".aepx-iteration-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def advance_locked(path, *, number, stage, evidence):
    """Single-host serialized read/transition/write; stale locks fail closed.

    Not a distributed lease or multi-worker fencing mechanism.
    """
    try:
        from scripts.aepx_pilot_checkpoint import exclusive_checkpoint_lock
    except ModuleNotFoundError:
        from aepx_pilot_checkpoint import exclusive_checkpoint_lock
    path = Path(path)
    if not path.is_absolute() or path.parent.is_symlink() or not path.parent.is_dir() or path.is_symlink():
        raise TransitionDenied("unsafe ledger destination")
    with exclusive_checkpoint_lock(path):
        state = load(path)
        updated = advance(state, number=number, stage=stage, evidence=evidence)
        persist(path, updated)
        return updated
