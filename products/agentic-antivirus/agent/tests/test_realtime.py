"""Real-time pre-open / pre-execute blocking (AV-01, VIS-01, B-01). The Linux tests use real fanotify permission
events and are skipped only where the kernel or privileges do not allow them."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "detection"))
from aav_detection import Engine  # noqa: E402

from aav_agent import realtime  # noqa: E402

BAD = b"#!/bin/sh\necho aav-realtime-test-malware-sample\n"
BAD_SHA = hashlib.sha256(BAD).hexdigest()
PATTERN = b"AAV-BYTE-SIGNATURE-PROBE"


def engine():
    return Engine({"hash_signatures": [{"id": "test.hash", "sha256": BAD_SHA, "name": "Test.Malware", "severity": "high"}],
                   "byte_signatures": [{"id": "test.bytes", "pattern_hex": PATTERN.hex(), "name": "Test.Bytes",
                                        "severity": "high"}],
                   "reputation": {}, "behaviour_rules": []}, "t-1")


def service(blocks, excluded=lambda p, s=None: False, own=None):
    return realtime.VerdictService(engine, excluded, lambda *a: blocks.append(a), own_pids=own or set())


def test_verdict_service_scans_descriptors_caches_and_fails_open(tmp_path):
    blocks = []
    svc = service(blocks)
    bad, good, sig = tmp_path / "bad.sh", tmp_path / "good.txt", tmp_path / "doc.bin"
    bad.write_bytes(BAD)
    good.write_text("hello")
    sig.write_bytes(b"x" * 5000 + PATTERN + b"y" * 10)
    assert svc.decide_path(str(bad), 1, "exec").allow is False
    assert svc.decide_path(str(sig), 1, "open").allow is False
    assert svc.decide_path(str(good), 1, "open").allow is True
    assert svc.decide_path(str(good), 1, "open").allow is True
    assert svc.stats["cache_hits"] == 1
    assert realtime.wait_until(lambda: len(blocks) == 2)
    assert {b[3] for b in blocks} == {"pre_exec_block", "pre_open_block"}
    assert svc.decide_path(str(tmp_path / "missing"), 1, "open").allow is True          # fail open
    assert service([], excluded=lambda p, s=None: p.endswith("bad.sh")).decide_path(str(bad), 1, "exec").allow
    assert service([], own={42}).decide_path(str(bad), 42, "exec").reason == "agent"
    bad.write_bytes(b"#!/bin/sh\necho now clean\n")                                       # mtime/size change
    assert svc.decide_path(str(bad), 1, "exec").allow is True


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or sys.platform == "win32", reason="Unix sockets")
def test_macos_verdict_socket_protocol(tmp_path):
    blocks = []
    sock_path = str(tmp_path / "v.sock")
    srv = realtime.VerdictSocketServer(service(blocks), sock_path).start()
    try:
        assert stat.S_IMODE(os.stat(sock_path).st_mode) == 0o600
        (tmp_path / "bad").write_bytes(BAD)
        c = socket.socket(socket.AF_UNIX)
        c.connect(sock_path)
        f = c.makefile("rwb")
        for req in ({"path": str(tmp_path / "bad"), "pid": 7, "op": "exec"}, {"path": "/etc/hostname", "op": "open"}):
            f.write(json.dumps(req).encode() + b"\n")
            f.flush()
        r1, r2 = json.loads(f.readline()), json.loads(f.readline())
        f.write(b"not json\n")
        f.flush()
        assert json.loads(f.readline())["allow"] is True                                   # bad request: fail open
        c.close()
        assert r1 == {"allow": False, "reason": "Test.Malware"} and r2["allow"] is True
    finally:
        srv.stop()


def test_windows_wire_layout_matches_the_driver_header():
    from aav_agent import realtime_windows as w
    assert ctypes.sizeof(w.AAV_REQUEST) == 8 + 2 * w.MAX_PATH_CHARS if ctypes.sizeof(ctypes.c_wchar) == 2 else True
    assert ctypes.sizeof(w.FILTER_MESSAGE_HEADER) == 16 and ctypes.sizeof(w.FILTER_REPLY_HEADER) == 16
    assert w.dos_path("\\??\\C:\\Users\\a.exe") == "C:\\Users\\a.exe"
    assert w.dos_path("\\Device\\HarddiskVolume3\\Users\\a.exe", {"\\device\\harddiskvolume3": "C:"}) == \
        "C:\\Users\\a.exe"
    header = (Path(__file__).resolve().parents[1] / "kernel" / "windows" / "AavProtocol.h").read_text()
    assert f"#define AAV_MAX_PATH_CHARS {w.MAX_PATH_CHARS}" in header
    assert 'L"\\\\AavFilterPort"' in header


def _fanotify_ok() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    from aav_agent import realtime_linux
    try:
        g = realtime_linux.FanotifyGuard(service([]), [tempfile.gettempdir()], mode="dir").start()
        g.stop()
        return True
    except realtime_linux.Unavailable:
        return False


linux_only = pytest.mark.skipif(not _fanotify_ok(), reason="fanotify permission events need Linux root/CAP_SYS_ADMIN")


def _child(code: str) -> subprocess.CompletedProcess:
    # A separate process: the guard always allows the agent's own process.
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)


@linux_only
def test_fanotify_blocks_open_and_exec_before_they_happen(tmp_path):
    from aav_agent.realtime_linux import FanotifyGuard
    blocks = []
    d = tmp_path / "Downloads"
    d.mkdir()
    bad, good = d / "invoice.sh", d / "notes.txt"
    bad.write_bytes(BAD)
    bad.chmod(0o755)
    good.write_text("hello")
    g = FanotifyGuard(service(blocks, own={os.getpid()}), [str(d)], mode="dir").start()
    try:
        r = _child(f"open({str(bad)!r}).read()")
        assert r.returncode != 0 and "PermissionError" in r.stderr                    # read blocked
        assert _child(f"print(open({str(good)!r}).read())").stdout.strip() == "hello"    # clean file unaffected
        with pytest.raises(PermissionError):
            subprocess.run([str(bad)], check=False, timeout=20)                         # execute blocked
        assert realtime.wait_until(lambda: len(blocks) >= 1)
        assert blocks[0][0] == str(bad) and blocks[0][1] == BAD_SHA
    finally:
        g.stop()
    assert _child(f"open({str(bad)!r}).read()").returncode == 0                         # guard gone: allowed again


@linux_only
def test_fanotify_mount_mode_scopes_opens_to_protected_roots(tmp_path):
    from aav_agent.realtime_linux import FanotifyGuard
    prot, other = tmp_path / "prot", tmp_path / "other"
    prot.mkdir()
    other.mkdir()
    (prot / "a.bin").write_bytes(b"z" + PATTERN)
    (other / "a.bin").write_bytes(b"z" + PATTERN)
    g = FanotifyGuard(service([], own={os.getpid()}), [str(prot)], mode="mount", block_exec=False).start()
    try:
        assert _child(f"open({str(prot / 'a.bin')!r}).read()").returncode != 0
        assert _child(f"open({str(other / 'a.bin')!r}).read()").returncode == 0           # outside the roots
    finally:
        g.stop()


def test_agent_reports_the_realtime_backend(tmp_path, monkeypatch):
    from aav_agent.agent import Agent
    a = Agent(str(tmp_path / "state"), base_url="http://127.0.0.1:9")
    monkeypatch.setattr(sys, "platform", "sunos5")
    assert a.start_realtime() == "unavailable: no backend for sunos5"
    assert a.start_realtime() == "unavailable: no backend for sunos5"
    ev = [b for _, b in a.state.pending_events(10)]
    assert any(e["kind"] == "realtime_protection" for e in ev)
