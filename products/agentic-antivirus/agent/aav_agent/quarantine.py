"""Quarantine vault (AV-02): quarantined files are encrypted at rest (AES-256-GCM with a
per-agent key) so they cannot execute or be opened in place; investigation metadata is kept.
Restore requires a fresh scan with the current engine; a dirty rescan keeps the item."""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Vault:
    def __init__(self, state):
        self.state = state
        self.dir = Path(state.root) / "quarantine"
        key = state.get("vault_key")
        if not key:
            key = secrets.token_hex(32)
            state.put("vault_key", key)
        self.aes = AESGCM(bytes.fromhex(key))

    def quarantine(self, path: str, sha256: str, detection) -> dict:
        src = Path(path)
        data = src.read_bytes()
        local_id = uuid.uuid4().hex
        nonce = secrets.token_bytes(12)
        (self.dir / f"{local_id}.bin").write_bytes(nonce + self.aes.encrypt(nonce, data, local_id.encode()))
        meta = {"local_id": local_id, "original_path": str(src.resolve()), "sha256": sha256,
                "detection": detection.title, "rule_id": detection.rule_id, "rule_version": detection.rule_version,
                "quarantined_at": time.time(), "size": len(data),
                "mode": oct(os.stat(src).st_mode & 0o777)}
        (self.dir / f"{local_id}.json").write_text(json.dumps(meta))
        src.unlink()
        return meta

    def items(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.dir.glob("*.json"))]

    def _plain(self, local_id: str) -> bytes:
        raw = (self.dir / f"{local_id}.bin").read_bytes()
        return self.aes.decrypt(raw[:12], raw[12:], local_id.encode())

    def restore(self, local_id: str, engine) -> dict:
        if not (self.dir / f"{local_id}.json").exists():
            return {"restored": False, "reason": "unknown quarantine item", "rescan": {"clean": None}}
        meta = json.loads((self.dir / f"{local_id}.json").read_text())
        data = self._plain(local_id)
        verdict = engine.scan_bytes(data) if engine else None
        rescan = {"clean": engine is not None and verdict is None,
                  "engine_version": engine.version if engine else None,
                  "detection": verdict.rule_id if verdict else None}
        if not rescan["clean"]:
            return {"restored": False, "reason": "fresh scan not clean" if engine else "no engine", "rescan": rescan}
        dest = Path(meta["original_path"])
        if dest.exists():
            return {"restored": False, "reason": "a file now exists at the original path", "rescan": rescan}
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, int(meta.get("mode", "0o600"), 8))
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        (self.dir / f"{local_id}.bin").unlink()
        (self.dir / f"{local_id}.json").unlink()
        return {"restored": True, "path": str(dest), "rescan": rescan}
