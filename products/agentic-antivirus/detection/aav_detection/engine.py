"""Detection engine shared by the endpoint agent and the control plane's file scanning.

Trace: ARC-03 (signatures + reputation + behavioural rules; every detection versioned and
carries the rule version and evidence used), AV-01, EDR-01, SEC-02, THR-04, THR-06, THR-08,
THR-09, VFS-12.

Bundle format (validated by validate_bundle):
  hash_signatures:  [{id, sha256, name, severity}]
  byte_signatures:  [{id, name, pattern_hex, max_offset, severity}]
  reputation:       {block_sha256: [], trusted_sha256: [], malicious_domains: [], malicious_urls: []}
  behaviour_rules:  [{id, version, title, technique, severity, kind, any|all: [{field, regex|equals|in}],
                      threshold?: {count, window_s, group_by}}]
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse

SEVERITIES = ("low", "medium", "high", "critical")
READ_CHUNK = 1024 * 1024


def _pread(fd: int, n: int, off: int) -> bytes:
    """os.pread where available (Linux, macOS); on Windows, seek and read the same descriptor.
    The Windows minifilter hands the service a handle it owns, so moving its offset is safe."""
    if hasattr(os, "pread"):
        return os.pread(fd, n, off)
    os.lseek(fd, off, os.SEEK_SET)
    return os.read(fd, n)


@dataclass
class Detection:
    rule_id: str
    rule_version: str
    title: str
    severity: str
    technique: str | None = None
    known_malware: bool = False
    matched: dict = field(default_factory=dict)
    evidence_event_uids: list = field(default_factory=list)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def validate_bundle(kind: str, body: dict) -> None:
    if kind == "agent":
        _require(isinstance(body.get("artifacts"), list) and body["artifacts"], "agent bundle needs artifacts")
        for a in body["artifacts"]:
            _require(set(a) >= {"platform", "url", "sha256"}, "artifact needs platform, url, sha256")
            _require(re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) is not None, "artifact sha256 invalid")
        return
    _require(kind == "detections", "unknown bundle kind")
    allowed = {"hash_signatures", "byte_signatures", "reputation", "behaviour_rules"}
    _require(set(body) <= allowed, f"unknown keys: {sorted(set(body) - allowed)}")
    ids: set[str] = set()
    for s in body.get("hash_signatures", []):
        _require(re.fullmatch(r"[0-9a-f]{64}", s.get("sha256", "")) is not None, "hash signature sha256 invalid")
        _require(s.get("severity") in SEVERITIES, "invalid severity")
        _require(s.get("id") not in ids, f"duplicate rule id {s.get('id')}")
        ids.add(s["id"])
    for s in body.get("byte_signatures", []):
        bytes.fromhex(s["pattern_hex"])
        _require(len(s["pattern_hex"]) >= 16, "byte pattern too short (min 8 bytes)")
        _require(s.get("severity") in SEVERITIES, "invalid severity")
        _require(s.get("id") not in ids, f"duplicate rule id {s.get('id')}")
        ids.add(s["id"])
    for r in body.get("behaviour_rules", []):
        _require(r.get("severity") in SEVERITIES, "invalid severity")
        _require(r.get("id") not in ids, f"duplicate rule id {r.get('id')}")
        ids.add(r["id"])
        _require(isinstance(r.get("version"), str), "behaviour rule needs a version")
        conds = r.get("any", []) + r.get("all", [])
        _require(bool(conds) or "threshold" in r, "behaviour rule needs conditions")
        for c in conds:
            if "regex" in c:
                re.compile(c["regex"])
    rep = body.get("reputation", {})
    for k in rep:
        _require(k in ("block_sha256", "trusted_sha256", "malicious_domains", "malicious_urls"),
                 f"unknown reputation list {k}")


class Engine:
    def __init__(self, bundle: dict, version: str):
        validate_bundle("detections", bundle)
        self.version = version
        self.hashes = {s["sha256"]: s for s in bundle.get("hash_signatures", [])}
        self.bytesigs = [(s, bytes.fromhex(s["pattern_hex"])) for s in bundle.get("byte_signatures", [])]
        rep = bundle.get("reputation", {})
        self.block = set(rep.get("block_sha256", []))
        self.trusted = set(rep.get("trusted_sha256", []))
        self.bad_domains = {d.lower().rstrip(".") for d in rep.get("malicious_domains", [])}
        self.bad_urls = set(rep.get("malicious_urls", []))
        self.rules = []
        for r in bundle.get("behaviour_rules", []):
            compiled = {k: [dict(c, _re=re.compile(c["regex"], re.I) if "regex" in c else None)
                            for c in r.get(k, [])] for k in ("any", "all")}
            self.rules.append((r, compiled))
        self._windows: dict = defaultdict(deque)
        self._max_pattern = max((len(p) for _, p in self.bytesigs), default=0)

    # ---------------------------------------------------------------- files
    def scan_bytes(self, data: bytes, sha256: str | None = None) -> Detection | None:
        sha256 = sha256 or hashlib.sha256(data).hexdigest()
        return self._hash_verdict(sha256) or self._byte_verdict_chunks([data], sha256)

    def scan_file(self, path: str) -> tuple[str, Detection | None]:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(READ_CHUNK), b""):
                h.update(chunk)
        sha = h.hexdigest()
        verdict = self._hash_verdict(sha)
        if verdict or sha in self.trusted:
            return sha, verdict
        with open(path, "rb") as fh:
            return sha, self._byte_verdict_chunks(iter(lambda: fh.read(READ_CHUNK), b""), sha)

    def scan_fd(self, fd: int, max_bytes: int | None = None) -> tuple[str | None, Detection | None]:
        """Scan an already-open file descriptor with pread (never re-opens the path). Used by the real-time guards,
        whose event descriptors must not trigger new open events. Returns (None, None) past max_bytes."""
        size = os.fstat(fd).st_size
        if max_bytes is not None and size > max_bytes:
            return None, None

        def chunks():
            off = 0
            while True:
                b = _pread(fd, READ_CHUNK, off)
                if not b:
                    return
                off += len(b)
                yield b
        h = hashlib.sha256()
        for c in chunks():
            h.update(c)
        sha = h.hexdigest()
        verdict = self._hash_verdict(sha)
        if verdict or sha in self.trusted:
            return sha, verdict
        return sha, self._byte_verdict_chunks(chunks(), sha)

    def _hash_verdict(self, sha256: str) -> Detection | None:
        if sha256 in self.trusted:
            return None
        s = self.hashes.get(sha256)
        if s:
            return Detection(s["id"], self.version, s["name"], s["severity"], "T1204", True, {"sha256": sha256})
        if sha256 in self.block:
            return Detection("reputation.block", self.version, "Blocked by reputation", "high", None, True,
                             {"sha256": sha256})
        return None

    def _byte_verdict_chunks(self, chunks: Iterable[bytes], sha256: str) -> Detection | None:
        if not self.bytesigs:
            return None
        offset, tail = 0, b""
        for chunk in chunks:
            window = tail + chunk
            base = offset - len(tail)
            for s, pat in self.bytesigs:
                idx = window.find(pat)
                if idx >= 0 and base + idx <= s.get("max_offset", 1 << 62):
                    return Detection(s["id"], self.version, s["name"], s["severity"], "T1204", True,
                                     {"sha256": sha256, "offset": base + idx})
            offset += len(chunk)
            tail = window[-(self._max_pattern - 1):] if self._max_pattern > 1 else b""
        return None

    # ---------------------------------------------------------------- urls
    def check_url(self, url: str) -> Detection | None:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        if url in self.bad_urls or any(host == d or host.endswith("." + d) for d in self.bad_domains):
            return Detection("reputation.url", self.version, "Known malicious URL", "high", "T1566",
                             matched={"url": url, "host": host})
        return None

    # ---------------------------------------------------------------- behaviour
    @staticmethod
    def _cond(c: dict, ev: dict) -> bool:
        val = ev.get(c["field"])
        if val is None:
            return False
        if c.get("_re") is not None:
            return bool(c["_re"].search(str(val)))
        if "equals" in c:
            return str(val).lower() == str(c["equals"]).lower()
        if "in" in c:
            return str(val).lower() in {str(x).lower() for x in c["in"]}
        return False

    def evaluate_event(self, ev: dict) -> list[Detection]:
        """ev: {event_uid, kind, ts (epoch s), ...fields}. Returns zero or more detections."""
        out = []
        for r, comp in self.rules:
            if r.get("kind") and r["kind"] != ev.get("kind"):
                continue
            if comp["all"] and not all(self._cond(c, ev) for c in comp["all"]):
                continue
            if comp["any"] and not any(self._cond(c, ev) for c in comp["any"]):
                continue
            th = r.get("threshold")
            if th:
                key = (r["id"], str(ev.get(th.get("group_by", "pid"))))
                win = self._windows[key]
                win.append((ev.get("ts", 0), ev.get("event_uid")))
                while win and ev.get("ts", 0) - win[0][0] > th["window_s"]:
                    win.popleft()
                if len(win) < th["count"]:
                    continue
                uids = [u for _, u in win]
                win.clear()
            else:
                uids = [ev.get("event_uid")]
            out.append(Detection(r["id"], r["version"], r["title"], r["severity"], r.get("technique"),
                                 matched={k: ev.get(k) for k in ("process", "pid", "cmdline", "path", "parent")
                                          if ev.get(k) is not None},
                                 evidence_event_uids=[u for u in uids if u]))
        return out
