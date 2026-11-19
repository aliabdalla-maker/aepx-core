"""Sandbox runner tests. The isolation tests start real containers and are skipped when Docker is
not available; set RUNNER_TEST_IMAGE to an image that has python3 and node."""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sandbox  # noqa: E402

PY = [{"path": "main.py", "content": "print('hi')"}]


# ------------------------------------------------------------------ request validation (no Docker)
def test_rejects_unsafe_paths_and_unknown_languages(monkeypatch):
    monkeypatch.setenv("RUNNER_ALLOW_RUNC", "true"); monkeypatch.setenv("RUNNER_RUNTIME", "runc")
    for bad in ["../x.py", "/etc/passwd.py", "a//b.py", "a\\b.py", ""]:
        with pytest.raises(sandbox.SandboxError):
            sandbox.run([{"path": "x.py", "content": ""}], bad)
    with pytest.raises(sandbox.SandboxError, match="Only Python"):
        sandbox.run([{"path": "x.sh", "content": "ls"}], "x.sh")
    with pytest.raises(sandbox.SandboxError, match="not in the project"):
        sandbox.run(PY, "other.py")
    with pytest.raises(sandbox.SandboxError, match="too large"):
        sandbox.run([{"path": "main.py", "content": "x" * 2_000_001}], "main.py")


def test_refuses_plain_runc_unless_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("RUNNER_RUNTIME", "runc"); monkeypatch.delenv("RUNNER_ALLOW_RUNC", raising=False)
    with pytest.raises(sandbox.SandboxError, match="gVisor"):
        sandbox.run(PY, "main.py")


def test_container_flags_lock_everything_down():
    args = sandbox.docker_args("n", "/w", "python", "main.py", sandbox.Limits(), "runsc")
    joined = " ".join(args)
    for flag in ["--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--user 65534:65534", "--runtime runsc", "--pids-limit 64", "--memory 256m",
                 "--memory-swap 256m", "readonly", "noexec"]:
        assert flag in joined
    assert "--privileged" not in joined and "docker.sock" not in joined


def test_timeout_kills_and_reports(monkeypatch):
    monkeypatch.setenv("RUNNER_ALLOW_RUNC", "true"); monkeypatch.setenv("RUNNER_RUNTIME", "runc")
    killed = []
    monkeypatch.setattr(sandbox.subprocess, "run", lambda args, **k: killed.append(args))
    def slow(args, **kw):
        raise subprocess.TimeoutExpired(args, kw["timeout"], output=b"partial", stderr=b"")
    r = sandbox.run(PY, "main.py", executor=slow, limits=sandbox.Limits(timeout_s=1))
    assert r.timed_out and r.exit_code is None and r.stdout == "partial"
    assert "time limit" in r.stderr and killed and killed[0][:2] == ["docker", "kill"]


# ------------------------------------------------------------------ HMAC request signing
def test_signature_required_and_replay_refused(monkeypatch):
    from fastapi import HTTPException
    import app as runner
    monkeypatch.setenv("RUNNER_SHARED_SECRET", "s" * 40)
    body = json.dumps({"entry": "main.py"}).encode()
    ts = str(int(time.time()))
    good = {"x-aepx-timestamp": ts, "x-aepx-signature": runner.sign(b"s" * 40, ts, body)}
    runner.verify(good, body)
    with pytest.raises(HTTPException) as e:
        runner.verify(good, body)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException):
        runner.verify({**good, "x-aepx-signature": "0" * 64}, body)
    old = str(int(time.time()) - 600)
    with pytest.raises(HTTPException):
        runner.verify({"x-aepx-timestamp": old, "x-aepx-signature": runner.sign(b"s" * 40, old, body)}, body)
    monkeypatch.setenv("RUNNER_SHARED_SECRET", "short")
    with pytest.raises(HTTPException) as e:
        runner.verify(good, body)
    assert e.value.status_code == 503


# ------------------------------------------------------------------ real containers
IMAGE = os.getenv("RUNNER_TEST_IMAGE", "")
docker_ok = bool(IMAGE) and shutil.which("docker") and subprocess.run(
    ["docker", "info"], capture_output=True).returncode == 0
real = pytest.mark.skipif(not docker_ok, reason="needs Docker and RUNNER_TEST_IMAGE")


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("RUNNER_IMAGE_PYTHON", IMAGE); monkeypatch.setenv("RUNNER_IMAGE_NODE", IMAGE)
    monkeypatch.setenv("RUNNER_RUNTIME", os.getenv("RUNNER_TEST_RUNTIME", "runc"))
    monkeypatch.setenv("RUNNER_ALLOW_RUNC", "true")
    return sandbox.Limits(timeout_s=5)


def py(code, stdin="", limits=None):
    return sandbox.run([{"path": "src/main.py", "content": code}, {"path": "src/util.py", "content": "X = 41\n"}],
                       "src/main.py", stdin=stdin, limits=limits)


@real
def test_real_python_output_exit_code_and_imports(live):
    r = py("import sys\nfrom util import X\nprint(X + 1)\nprint(sys.stdin.read().upper())\nsys.exit(3)", "abc", live)
    assert r.stdout.split() == ["42", "ABC"] and r.exit_code == 3 and not r.timed_out


@real
def test_real_node_output(live):
    r = sandbox.run([{"path": "a.js", "content": "console.log(6*7); process.exitCode = 2"}], "a.js", limits=live)
    assert r.stdout.strip() == "42" and r.exit_code == 2


@real
def test_real_no_network(live):
    r = py("import socket\ntry:\n  socket.create_connection(('1.1.1.1', 53), timeout=2); print('CONNECTED')\n"
           "except OSError as e:\n  print('blocked', type(e).__name__)", limits=live)
    assert "blocked" in r.stdout and "CONNECTED" not in r.stdout


@real
def test_real_read_only_project_and_root(live):
    r = py("import os\nfor p in ['/work/src/main.py', '/etc/x', '/usr/x']:\n"
           "  try:\n    open(p, 'a').write('x'); print('WROTE', p)\n  except OSError as e:\n    print('denied', p)\n"
           "open('/tmp/ok', 'w').write('fine'); print('tmp ok')\nprint('uid', os.getuid())", limits=live)
    assert "WROTE" not in r.stdout and "tmp ok" in r.stdout and "uid 65534" in r.stdout


@real
def test_real_timeout_is_enforced(live):
    t = time.monotonic()
    r = py("while True: pass", limits=sandbox.Limits(timeout_s=2))
    assert r.timed_out and time.monotonic() - t < 15
    assert subprocess.run(["docker", "ps", "-q", "--filter", "name=aepx-run-"], capture_output=True, text=True).stdout.strip() == ""


@real
def test_real_memory_and_process_limits(live):
    r = py("x = bytearray(600 * 1024 * 1024)\nprint('ALLOCATED')", limits=live)
    assert "ALLOCATED" not in r.stdout and r.exit_code != 0
    r = py("import os\nn=0\ntry:\n  for _ in range(500):\n    if os.fork() == 0:\n      import time; time.sleep(3); os._exit(0)\n"
           "    n += 1\nexcept OSError:\n  pass\nprint('forked', n)", limits=live)
    forked = int(r.stdout.split()[-1]) if r.stdout.strip() else 0
    assert forked < 64


@real
def test_real_output_is_capped(live):
    r = py("print('y' * 500000)", limits=sandbox.Limits(timeout_s=5, output_bytes=1000))
    assert r.truncated and len(r.stdout) <= 1000
