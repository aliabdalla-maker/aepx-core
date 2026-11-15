"""Run untrusted project code in a throw-away, locked-down container.

Every run gets a fresh container that has:
  * no network (--network none) and no Linux capabilities, no-new-privileges;
  * a read-only root filesystem; the project is mounted read-only at /work and
    only a small, noexec /tmp is writable;
  * an unprivileged user (65534), CPU, memory, swap, process and open-file limits;
  * a hard wall-clock timeout, after which the container is killed;
  * capped stdout/stderr.
With RUNNER_RUNTIME=runsc (gVisor) the container also gets its own user-space kernel.
Plain runc is refused unless RUNNER_ALLOW_RUNC=true, which is for local testing only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

LANGUAGES = {
    "python": {"ext": (".py",), "image_env": "RUNNER_IMAGE_PYTHON", "default_image": "python:3.12-alpine",
               # -E -s: ignore PYTHON* variables and user site-packages, but keep the script's own
               # folder importable (-I would break multi-file projects).
               "cmd": ["python3", "-E", "-s", "-B"]},
    "node": {"ext": (".js", ".mjs", ".cjs"), "image_env": "RUNNER_IMAGE_NODE", "default_image": "node:22-alpine",
             "cmd": ["node", "--disallow-code-generation-from-strings"]},
}
MAX_FILES = 300
MAX_TOTAL_BYTES = 2_000_000
MAX_STDIN = 64_000


class SandboxError(ValueError):
    """Request rejected before anything ran."""


@dataclass
class Limits:
    timeout_s: float = 10.0
    memory_mb: int = 256
    cpus: float = 0.5
    pids: int = 64
    output_bytes: int = 64_000
    tmp_mb: int = 32

    @classmethod
    def from_env(cls) -> "Limits":
        def num(name, default, lo, hi, kind=float):
            try:
                value = kind(os.getenv(name, default))
            except ValueError:
                value = kind(default)
            return min(max(value, lo), hi)
        return cls(timeout_s=num("RUNNER_TIMEOUT_SECONDS", 10, 1, 60),
                   memory_mb=num("RUNNER_MEMORY_MB", 256, 64, 2048, int),
                   cpus=num("RUNNER_CPUS", 0.5, 0.1, 2),
                   pids=num("RUNNER_PIDS", 64, 16, 512, int),
                   output_bytes=num("RUNNER_OUTPUT_BYTES", 64_000, 1_000, 1_000_000, int),
                   tmp_mb=num("RUNNER_TMP_MB", 32, 8, 256, int))


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    truncated: bool = False
    runtime: str = ""
    language: str = ""
    extra: dict = field(default_factory=dict)


def safe_relative(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 255 or "\\" in path or "\0" in path:
        raise SandboxError("Invalid file path")
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ("", ".", "..") for part in path.split("/")):
        raise SandboxError("Invalid file path")
    return str(p)


def language_for(entry: str, requested: str | None = None) -> str:
    entry = entry.lower()
    for name, spec in LANGUAGES.items():
        if entry.endswith(spec["ext"]) and (requested in (None, "", name)):
            return name
    raise SandboxError("Only Python (.py) and JavaScript (.js, .mjs, .cjs) files can be run")


def validate(files: list[dict], entry: str) -> list[tuple[str, str]]:
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        raise SandboxError(f"Send between 1 and {MAX_FILES} files")
    out, total, seen = [], 0, set()
    for f in files:
        path = safe_relative(f.get("path", ""))
        content = f.get("content", "")
        if not isinstance(content, str):
            raise SandboxError("File content must be text")
        total += len(content.encode())
        if total > MAX_TOTAL_BYTES:
            raise SandboxError("Project too large to run (over 2 MB of files)")
        if path in seen:
            raise SandboxError("Duplicate file path")
        seen.add(path)
        out.append((path, content))
    if safe_relative(entry) not in seen:
        raise SandboxError("The file to run is not in the project")
    return out


def runtime() -> str:
    rt = os.getenv("RUNNER_RUNTIME", "runsc")
    if rt != "runsc" and os.getenv("RUNNER_ALLOW_RUNC") != "true":
        raise SandboxError("Refusing to run without gVisor (set RUNNER_RUNTIME=runsc)")
    return rt


def docker_args(name: str, workdir: str, language: str, entry: str, limits: Limits, rt: str) -> list[str]:
    spec = LANGUAGES[language]
    image = os.getenv(spec["image_env"], spec["default_image"])
    return [
        "docker", "run", "--rm", "-i", "--name", name, "--runtime", rt,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--memory", f"{limits.memory_mb}m", "--memory-swap", f"{limits.memory_mb}m",
        "--cpus", str(limits.cpus), "--pids-limit", str(limits.pids),
        "--ulimit", "nofile=128:128", "--ulimit", "fsize=16777216:16777216",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={limits.tmp_mb}m,mode=1777",
        "--mount", f"type=bind,source={workdir},target=/work,readonly",
        "--workdir", "/work", "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--log-driver", "none", "--stop-timeout", "1",
        image, *spec["cmd"], entry,
    ]


def _cap(data: bytes, limit: int) -> tuple[str, bool]:
    return data[:limit].decode("utf-8", "replace"), len(data) > limit


def run(files: list[dict], entry: str, *, language: str | None = None, stdin: str = "",
        limits: Limits | None = None, executor=subprocess.run) -> RunResult:
    limits = limits or Limits.from_env()
    entry = safe_relative(entry)
    lang = language_for(entry, language)
    checked = validate(files, entry)
    if len(stdin) > MAX_STDIN:
        raise SandboxError("Input too large")
    rt = runtime()
    # The bind-mount source must be a path the Docker daemon can see (a shared volume when the
    # runner itself runs in a container).
    workdir = tempfile.mkdtemp(prefix="aepx-run-", dir=os.getenv("RUNNER_WORK_ROOT") or None)
    os.chmod(workdir, 0o755)
    name = "aepx-run-" + uuid.uuid4().hex[:16]
    try:
        for path, content in checked:
            target = os.path.join(workdir, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(target, 0o644)
        for root, dirs, _ in os.walk(workdir):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
        args = docker_args(name, workdir, lang, entry, limits, rt)
        started = time.monotonic()
        timed_out = False
        try:
            proc = executor(args, input=stdin.encode(), capture_output=True, timeout=limits.timeout_s)
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
            out, err, code = exc.stdout or b"", exc.stderr or b"", None
        duration = int((time.monotonic() - started) * 1000)
        stdout, t1 = _cap(out, limits.output_bytes)
        stderr, t2 = _cap(err, limits.output_bytes)
        if code == 137 and not timed_out:
            stderr += "\n[stopped: the program used more than its memory limit]"
        if timed_out:
            stderr += f"\n[stopped: time limit of {limits.timeout_s:g}s reached]"
        return RunResult(stdout, stderr, code, timed_out, duration, t1 or t2, rt, lang)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
