"""Fail-closed, atomic checkpoint ledger for supervised AEP-X offline pilot tests.

This is not an LLM agent. Only actual test attempts count; no deployment authority.
"""
import json
import os
import tempfile
from pathlib import Path

MAX_ITERATIONS = 10000
STATUSES = frozenset({"passed", "failed", "timeout"})

def validate(state):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("unsupported checkpoint schema")
    attempts = state.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > MAX_ITERATIONS:
        raise ValueError("invalid attempt ledger")
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict) or type(attempt.get("number")) is not int or attempt["number"] != index:
            raise ValueError("invalid attempt sequence")
        if attempt.get("status") not in STATUSES or not isinstance(attempt.get("pattern"), str):
            raise ValueError("invalid attempt metadata")
    if state.get("release_approved") is not False or state.get("auto_merge") is not False or state.get("auto_deploy") is not False:
        raise ValueError("unsafe checkpoint flags")
    return state

def initial():
    return {"schema_version": 1, "attempts": [], "release_approved": False,
            "auto_merge": False, "auto_deploy": False}

def load(path):
    path = Path(path)
    if not path.exists():
        return initial()
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe checkpoint path")
    return validate(json.loads(path.read_text(encoding="utf-8")))

def append(path, result):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("unsafe checkpoint destination")
    state = load(path)
    if len(state["attempts"]) >= MAX_ITERATIONS:
        raise ValueError("iteration cap reached")
    if not isinstance(result, dict) or result.get("status") not in STATUSES:
        raise ValueError("only actual test outcomes may be recorded")
    if not isinstance(result.get("pattern"), str) or not result["pattern"]:
        raise ValueError("missing test pattern")
    state["attempts"].append({"number": len(state["attempts"]) + 1,
                              "pattern": result["pattern"], "status": result["status"]})
    validate(state)
    fd, tmp = tempfile.mkstemp(prefix=".aepx-pilot-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return state
