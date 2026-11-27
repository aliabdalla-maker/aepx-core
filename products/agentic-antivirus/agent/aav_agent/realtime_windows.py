"""Windows pre-open / pre-execute blocking: user-mode side of the AavFilter minifilter (B-01 Windows, AV-01).

The kernel driver (agent/kernel/windows/AavFilter.c) holds IRP_MJ_CREATE for files opened for execute or read by
any process other than the agent, and sends an AAV_REQUEST over the filter communication port "\\AavFilterPort".
This client answers with AAV_REPLY {Allow} from realtime.VerdictService. If no reply arrives within the driver's
timeout (default 3 s) or the agent is not connected, the driver allows the open (fail open), so a stopped agent
never locks the machine. The wire layout must match agent/kernel/windows/AavProtocol.h.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from aav_agent.realtime import VerdictService

PORT_NAME = "\\AavFilterPort"
MAX_PATH_CHARS = 520
OP_OPEN, OP_EXEC = 1, 2


class FILTER_MESSAGE_HEADER(ctypes.Structure):
    _fields_ = [("ReplyLength", wintypes.ULONG), ("MessageId", ctypes.c_ulonglong)]


class AAV_REQUEST(ctypes.Structure):
    _fields_ = [("ProcessId", wintypes.ULONG), ("Operation", wintypes.ULONG),
                ("Path", ctypes.c_wchar * MAX_PATH_CHARS)]


class REQUEST_MESSAGE(ctypes.Structure):
    _fields_ = [("Header", FILTER_MESSAGE_HEADER), ("Request", AAV_REQUEST)]


class FILTER_REPLY_HEADER(ctypes.Structure):
    _fields_ = [("Status", ctypes.c_long), ("MessageId", ctypes.c_ulonglong)]


class AAV_REPLY(ctypes.Structure):
    _fields_ = [("Allow", wintypes.ULONG)]


class REPLY_MESSAGE(ctypes.Structure):
    _fields_ = [("Header", FILTER_REPLY_HEADER), ("Reply", AAV_REPLY)]


_DEVICE_MAP: dict[str, str] | None = None


def _device_map() -> dict[str, str]:
    """\\Device\\HarddiskVolumeN -> C: for every drive letter (QueryDosDeviceW)."""
    global _DEVICE_MAP
    if _DEVICE_MAP is None:
        m: dict[str, str] = {}
        k32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]
        buf = ctypes.create_unicode_buffer(1024)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if k32.QueryDosDeviceW(f"{letter}:", buf, len(buf)):
                m[buf.value.lower()] = f"{letter}:"
        _DEVICE_MAP = m
    return _DEVICE_MAP


def dos_path(nt_path: str, device_map: dict[str, str] | None = None) -> str:
    """The driver sends normalized NT names (\\Device\\HarddiskVolume3\\Users\\a.exe); map them to C:\\Users\\a.exe."""
    if nt_path.startswith("\\??\\"):
        return nt_path[4:]
    if nt_path.lower().startswith("\\device\\"):
        parts = nt_path.split("\\")
        dev = "\\".join(parts[:3]).lower()
        drive = (device_map if device_map is not None else _device_map()).get(dev)
        if drive:
            return drive + "\\" + "\\".join(parts[3:])
    return nt_path


class FilterPortClient:
    def __init__(self, service: VerdictService, workers: int = 4):
        self.service, self.workers = service, workers
        self.port = None

    def start(self) -> "FilterPortClient":
        flt = ctypes.WinDLL("fltlib.dll")  # type: ignore[attr-defined]
        port = wintypes.HANDLE()
        hr = flt.FilterConnectCommunicationPort(ctypes.c_wchar_p(PORT_NAME), 0, None, 0, None, ctypes.byref(port))
        if hr != 0:
            raise RuntimeError(f"AavFilter driver not reachable (HRESULT 0x{hr & 0xFFFFFFFF:08x}); "
                               "install and start it: sc start AavFilter")
        self.port, self._flt = port, flt
        for i in range(self.workers):
            threading.Thread(target=self._loop, name=f"aav-minifilter-{i}", daemon=True).start()
        return self

    def _loop(self) -> None:
        flt, port = self._flt, self.port
        while True:
            msg = REQUEST_MESSAGE()
            hr = flt.FilterGetMessage(port, ctypes.byref(msg.Header), ctypes.sizeof(msg), None)
            if hr != 0:
                return
            req = msg.Request
            op = "exec" if req.Operation == OP_EXEC else "open"
            d = self.service.decide_path(dos_path(req.Path), int(req.ProcessId), op)
            reply = REPLY_MESSAGE()
            reply.Header.Status = 0
            reply.Header.MessageId = msg.Header.MessageId
            reply.Reply.Allow = 1 if d.allow else 0
            flt.FilterReplyMessage(port, ctypes.byref(reply.Header),
                                   ctypes.sizeof(FILTER_REPLY_HEADER) + ctypes.sizeof(AAV_REPLY))
