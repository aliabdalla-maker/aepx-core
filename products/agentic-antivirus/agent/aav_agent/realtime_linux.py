"""Linux pre-open / pre-execute blocking with fanotify permission events (B-01 Linux, AV-01).

The agent (running as root with CAP_SYS_ADMIN, as the systemd unit does) creates a FAN_CLASS_CONTENT group and
marks either whole mounts (production: every open/exec on the filesystems that hold the protected paths) or
single directories (FAN_EVENT_ON_CHILD). For every event the kernel holds the opening process until we write
FAN_ALLOW or FAN_DENY; the decision comes from realtime.VerdictService, scanning the event's own descriptor.

Safety: if this thread dies or the agent exits, the kernel closes the group and allows every pending event, so a
fault can never leave the machine unable to open files. Events from the agent's own process are always allowed.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import select
import struct
import threading

from aav_agent.realtime import VerdictService

FAN_CLOEXEC = 0x1
FAN_NONBLOCK = 0x2
FAN_CLASS_CONTENT = 0x4
FAN_UNLIMITED_QUEUE = 0x10
FAN_MARK_ADD = 0x1
FAN_MARK_MOUNT = 0x10
FAN_OPEN_PERM = 0x10000
FAN_OPEN_EXEC_PERM = 0x40000
FAN_EVENT_ON_CHILD = 0x08000000
FAN_ALLOW = 0x1
FAN_DENY = 0x2
FAN_NOFD = -1
AT_FDCWD = -100
_META = struct.Struct("IBBHQii")      # struct fanotify_event_metadata
_RESP = struct.Struct("iI")           # struct fanotify_response


class Unavailable(RuntimeError):
    pass


def _libc():
    libc = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
    libc.fanotify_init.argtypes = [ctypes.c_uint, ctypes.c_uint]
    libc.fanotify_mark.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int, ctypes.c_char_p]
    return libc


class FanotifyGuard:
    def __init__(self, service: VerdictService, roots: list[str], *, mode: str = "mount",
                 block_open: bool = True, block_exec: bool = True):
        if mode not in ("mount", "dir"):
            raise ValueError("mode must be 'mount' or 'dir'")
        self.service, self.mode = service, mode
        self.roots = [os.path.realpath(r) for r in roots]
        self.mask = (FAN_OPEN_PERM if block_open else 0) | (FAN_OPEN_EXEC_PERM if block_exec else 0)
        self.fd: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> "FanotifyGuard":
        if os.name != "posix" or not hasattr(os, "pread"):
            raise Unavailable("fanotify needs Linux")
        libc = _libc()
        fd = libc.fanotify_init(FAN_CLASS_CONTENT | FAN_CLOEXEC | FAN_UNLIMITED_QUEUE,
                                os.O_RDONLY | getattr(os, "O_LARGEFILE", 0) | os.O_CLOEXEC)
        if fd < 0:
            e = ctypes.get_errno()
            raise Unavailable(f"fanotify_init: {os.strerror(e)} (needs root/CAP_SYS_ADMIN and a kernel with "
                              "CONFIG_FANOTIFY_ACCESS_PERMISSIONS)")
        flags = FAN_MARK_ADD | (FAN_MARK_MOUNT if self.mode == "mount" else 0)
        mask = self.mask | (FAN_EVENT_ON_CHILD if self.mode == "dir" else 0)
        for r in self.roots:
            if libc.fanotify_mark(fd, flags, mask, AT_FDCWD, r.encode()) != 0:
                e = ctypes.get_errno()
                os.close(fd)
                raise Unavailable(f"fanotify_mark {r}: {os.strerror(e)}")
        self.fd = fd
        self._thread = threading.Thread(target=self._loop, name="aav-fanotify", daemon=True)
        self._thread.start()
        return self

    def _in_scope(self, path: str) -> bool:
        return self.mode == "dir" or any(path == r or path.startswith(r.rstrip("/") + "/") for r in self.roots)

    def _loop(self) -> None:
        fd = self.fd
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.5)
                if not ready:
                    continue
                buf = os.read(fd, 64 * 1024)
            except (OSError, ValueError):
                return
            off = 0
            while off + _META.size <= len(buf):
                ev_len, _ver, _r, _mlen, mask, efd, pid = _META.unpack_from(buf, off)
                off += ev_len
                if efd == FAN_NOFD or efd < 0:
                    continue
                verdict = FAN_ALLOW
                try:
                    if mask & (FAN_OPEN_PERM | FAN_OPEN_EXEC_PERM):
                        try:
                            path = os.readlink(f"/proc/self/fd/{efd}")
                        except OSError:
                            path = ""
                        if (path and self._in_scope(path)) or mask & FAN_OPEN_EXEC_PERM:
                            op = "exec" if mask & FAN_OPEN_EXEC_PERM else "open"
                            if not self.service.decide_fd(efd, path, pid, op).allow:
                                verdict = FAN_DENY
                finally:
                    try:
                        os.write(fd, _RESP.pack(efd, verdict))
                    finally:
                        os.close(efd)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)          # any pending events are allowed by the kernel
