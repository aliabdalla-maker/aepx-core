"""Operating-system interfaces used by the agent: network isolation, process termination,
persistence locations, removable media.

Isolation preserves the management connection (EDR-02, RSP-06): the control-plane host and the
policy's allowed_management_hosts stay reachable; everything else is dropped until release or
expiry. Applying firewall rules needs administrator/root rights; without them the command fails
with that reason rather than reporting success.
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

import psutil

NFT_TABLE = "aav_isolation"


def _resolve(hosts: list[str]) -> list[str]:
    ips: set[str] = set()
    for h in hosts:
        try:
            for info in socket.getaddrinfo(h, None):
                ips.add(info[4][0])
        except socket.gaierror:
            continue
    return sorted(ips)


def isolation_commands(system: str, allow_ips: list[str]) -> list[list[str]]:
    v4 = [ip for ip in allow_ips if ":" not in ip]
    v6 = [ip for ip in allow_ips if ":" in ip]
    if system == "Linux":
        rules = [f"add table inet {NFT_TABLE}",
                 f"add chain inet {NFT_TABLE} out {{ type filter hook output priority -10 ; policy drop ; }}",
                 f"add chain inet {NFT_TABLE} in {{ type filter hook input priority -10 ; policy drop ; }}",
                 f"add rule inet {NFT_TABLE} out oif lo accept", f"add rule inet {NFT_TABLE} in iif lo accept",
                 f"add rule inet {NFT_TABLE} in ct state established,related accept",
                 f"add rule inet {NFT_TABLE} out ct state established,related accept",
                 f"add rule inet {NFT_TABLE} out udp dport 53 accept"]
        for ip in v4:
            rules.append(f"add rule inet {NFT_TABLE} out ip daddr {ip} accept")
        for ip in v6:
            rules.append(f"add rule inet {NFT_TABLE} out ip6 daddr {ip} accept")
        return [["nft", r] for r in rules]
    if system == "Windows":
        cmds = [["netsh", "advfirewall", "set", "allprofiles", "firewallpolicy", "blockinbound,blockoutbound"]]
        if allow_ips:
            cmds.append(["netsh", "advfirewall", "firewall", "add", "rule", "name=AAV-Isolation-Management",
                         "dir=out", "action=allow", f"remoteip={','.join(allow_ips)}"])
        cmds.append(["netsh", "advfirewall", "firewall", "add", "rule", "name=AAV-Isolation-DNS", "dir=out",
                     "action=allow", "protocol=UDP", "remoteport=53"])
        return cmds
    if system == "Darwin":
        anchor = "block drop all\npass quick on lo0 all\npass out proto udp to any port 53 keep state\n" + \
                 "".join(f"pass out quick to {ip} keep state\n" for ip in allow_ips)
        return [["sh", "-c", f"printf '%s' '{anchor}' | pfctl -a aav_isolation -f -"], ["pfctl", "-E"]]
    raise RuntimeError(f"isolation not supported on {system}")


def release_commands(system: str) -> list[list[str]]:
    if system == "Linux":
        return [["nft", f"delete table inet {NFT_TABLE}"]]
    if system == "Windows":
        return [["netsh", "advfirewall", "firewall", "delete", "rule", "name=AAV-Isolation-Management"],
                ["netsh", "advfirewall", "firewall", "delete", "rule", "name=AAV-Isolation-DNS"],
                ["netsh", "advfirewall", "set", "allprofiles", "firewallpolicy", "blockinbound,allowoutbound"]]
    if system == "Darwin":
        return [["pfctl", "-a", "aav_isolation", "-F", "all"]]
    raise RuntimeError(f"isolation not supported on {system}")


def is_privileged() -> bool:
    if os.name == "nt":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


def run(cmds: list[list[str]]) -> dict:
    if not is_privileged():
        return {"ok": False, "reason": "insufficient privileges to change the firewall"}
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"ok": False, "reason": f"{c[0]} failed: {r.stderr.strip()[:300]}"}
    return {"ok": True, "commands": len(cmds)}


def isolate(management_hosts: list[str]) -> dict:
    ips = _resolve(management_hosts)
    if not ips:
        return {"ok": False, "reason": "no management host resolved; refusing to isolate without a management path"}
    res = run(isolation_commands(platform.system(), ips))
    res["management_ips"] = ips
    return res


def release() -> dict:
    return run(release_commands(platform.system()))


def terminate(pid: int, image_sha256: str | None = None) -> dict:
    import hashlib
    try:
        proc = psutil.Process(pid)
        if image_sha256:
            exe = proc.exe()
            with open(exe, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != image_sha256:
                    return {"ok": False, "reason": "process image changed; target mismatch"}
        if pid in (0, 1, os.getpid()):
            return {"ok": False, "reason": "refusing to terminate a protected process"}
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            proc.kill()
        return {"ok": True, "pid": pid}
    except psutil.NoSuchProcess:
        return {"ok": True, "pid": pid, "note": "process already exited"}
    except psutil.AccessDenied:
        return {"ok": False, "reason": "access denied"}


def persistence_locations() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Linux":
        return [Path("/etc/cron.d"), Path("/var/spool/cron"), Path("/etc/systemd/system"), home / ".config/autostart",
                Path("/etc/crontab")]
    if system == "Darwin":
        return [home / "Library/LaunchAgents", Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons")]
    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA", home))
        return [appdata / "Microsoft/Windows/Start Menu/Programs/Startup"]
    return []


def windows_run_keys() -> dict:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        return {}
    import winreg
    out = {}
    for hive, name in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                        out[f"{name}\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{n}"] = str(v)
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    return out


def removable_mounts() -> set[str]:
    out = set()
    for part in psutil.disk_partitions(all=False):
        opts = part.opts.lower()
        if "removable" in opts or part.mountpoint.startswith(("/media/", "/run/media/", "/Volumes/")):
            out.add(part.mountpoint)
    return out
