"""Real-time (pre-open / pre-execute) protection — shared decision logic (AV-01, VIS-01, B-01, B-04).

Each platform backend asks one question before the operating system lets a process open or execute a file:
"allow or deny?". The backends are:
- Linux: fanotify permission events (FAN_OPEN_PERM, FAN_OPEN_EXEC_PERM) — realtime_linux.py, runs in the agent
- Windows: the AavFilter kernel minifilter (agent/kernel/windows) asks over a filter communication port —
  realtime_windows.py
- macOS: the Endpoint Security system extension (agent/kernel/macos) asks over a local Unix socket —
  VerdictSocketServer below

Rules: answers are fast (cache keyed on device, inode, size and mtime), fail open on internal errors or files
over the size limit (the post-write scanner still covers them, so a crash can never lock the user out of their
machine), never block the agent itself, honour policy exclusions, and hand every block to the agent's normal
response path (quarantine + detection event) off the hot path.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

MAX_SCAN_BYTES = 64 * 1024 * 1024
CACHE_SIZE = 50_000


@dataclass
class Decision:
    allow: bool
    reason: str
    sha256: str | None = None
    detection: object | None = None


class VerdictService:
    """Thread-safe allow/deny decisions shared by every backend."""

    def __init__(self, engine_fn: Callable[[], object | None], excluded: Callable[[str, str | None], bool],
                 on_block: Callable[[str, str, object, str], None], own_pids: set[int] | None = None,
                 max_scan_bytes: int = MAX_SCAN_BYTES):
        self.engine_fn, self.excluded, self.max_scan_bytes = engine_fn, excluded, max_scan_bytes
        self.own_pids = own_pids if own_pids is not None else {os.getpid()}
        self._cache: OrderedDict[tuple, tuple[str, Decision]] = OrderedDict()
        self._lock = threading.Lock()
        self._blocks: queue.Queue = queue.Queue()
        self._on_block = on_block
        self.stats = {"allowed": 0, "denied": 0, "errors": 0, "cache_hits": 0, "skipped_large": 0}
        threading.Thread(target=self._drain, name="aav-realtime-respond", daemon=True).start()

    def _drain(self) -> None:
        while True:
            path, sha, det, trigger = self._blocks.get()
            try:
                self._on_block(path, sha, det, trigger)
            except Exception:  # pragma: no cover - the block itself already happened
                self.stats["errors"] += 1

    def decide_fd(self, fd: int, path: str, pid: int, op: str) -> Decision:
        """op is 'open' or 'exec'. fd is an open descriptor for the file (never re-opened by path)."""
        if pid in self.own_pids:
            return Decision(True, "agent")
        try:
            st = os.fstat(fd)
            if not (st.st_mode & 0o170000 == 0o100000):        # regular files only
                return Decision(True, "not a regular file")
            key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
            eng = self.engine_fn()
            ver = getattr(eng, "version", None)
            with self._lock:
                hit = self._cache.get(key)
                if hit and hit[0] == ver:
                    self._cache.move_to_end(key)
                    self.stats["cache_hits"] += 1
                    return self._count(hit[1], path, op, cached=True)
            if eng is None:
                return self._count(Decision(True, "no verified detection bundle"), path, op)
            if self.excluded(path, None):
                return self._count(Decision(True, "excluded"), path, op)
            sha, det = eng.scan_fd(fd, self.max_scan_bytes)
            if sha is None:
                self.stats["skipped_large"] += 1
                return Decision(True, "over size limit; post-write scanner covers it")
            if det and not self.excluded(path, sha):
                d = Decision(False, det.title, sha, det)
            else:
                d = Decision(True, "clean", sha)
            with self._lock:
                self._cache[key] = (ver, d)
                if len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
            return self._count(d, path, op)
        except Exception:
            self.stats["errors"] += 1
            return Decision(True, "error (fail open)")

    def decide_path(self, path: str, pid: int, op: str) -> Decision:
        """For backends that pass a path (macOS socket protocol). Opens with O_NOFOLLOW; the caller (the ES
        extension) is the only process allowed to make this open without generating a new auth event."""
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        except OSError:
            return Decision(True, "unreadable (fail open)")
        try:
            return self.decide_fd(fd, path, pid, op)
        finally:
            os.close(fd)

    def _count(self, d: Decision, path: str, op: str, cached: bool = False) -> Decision:
        if d.allow:
            self.stats["allowed"] += 1
        else:
            self.stats["denied"] += 1
            if not cached:
                self._blocks.put((path, d.sha256, d.detection, f"pre_{op}_block"))
        return d


class VerdictSocketServer:
    """Unix-socket verdict endpoint for the macOS Endpoint Security extension. One JSON object per line:
    request {"path": str, "pid": int, "op": "open"|"exec"} -> reply {"allow": bool, "reason": str}.
    The socket is created mode 0600 and owned by root, so only the root-owned system extension can ask."""

    def __init__(self, service: VerdictService, sock_path: str):
        self.service, self.sock_path = service, sock_path
        self._srv: socket.socket | None = None

    def start(self) -> "VerdictSocketServer":
        try:
            os.unlink(self.sock_path)
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            srv.bind(self.sock_path)
        finally:
            os.umask(old)
        srv.listen(16)
        self._srv = srv
        threading.Thread(target=self._accept, name="aav-verdict-socket", daemon=True).start()
        return self

    def _accept(self) -> None:
        while self._srv:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn, conn.makefile("rwb") as f:
            for line in f:
                try:
                    req = json.loads(line)
                    d = self.service.decide_path(str(req["path"]), int(req.get("pid", 0)), str(req.get("op", "open")))
                    out = {"allow": d.allow, "reason": d.reason}
                except (ValueError, KeyError, TypeError):
                    out = {"allow": True, "reason": "bad request (fail open)"}
                f.write(json.dumps(out).encode() + b"\n")
                f.flush()

    def stop(self) -> None:
        s, self._srv = self._srv, None
        if s:
            s.close()
        try:
            os.unlink(self.sock_path)
        except FileNotFoundError:
            pass


def wait_until(pred: Callable[[], bool], timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()
