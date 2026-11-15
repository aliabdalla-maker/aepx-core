"""Run-code endpoint: off by default, role-checked, tenant-scoped, audited; and the full chain
API -> HMAC-signed request -> runner -> locked-down container when Docker is available."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.test_postgres_integration import headers, main, prepared_db, tokens  # noqa: F401
from app import execution

SECRET = "r" * 40


def project_with(client, token, files):
    h = headers(token, "alpha")
    pid = client.post("/api/v1/projects", json={"name": "run test"}, headers=h).json()["id"]
    for path, content in files.items():
        assert client.put(f"/api/v1/projects/{pid}/files/{path}", json={"content": content}, headers=h).status_code == 200
    return pid, h


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("IDE_CODE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IDE_RUNNER_URL", "https://runner.internal.test")
    monkeypatch.setenv("IDE_RUNNER_SECRET", SECRET)
    execution._recent.clear()


def test_off_by_default_says_why(prepared_db, tokens, monkeypatch):
    monkeypatch.delenv("IDE_CODE_EXECUTION_ENABLED", raising=False)
    client = TestClient(main.app)
    t = tokens()
    s = client.get("/api/v1/execution", headers=headers(t, "alpha")).json()
    assert s == {"enabled": False, "languages": [], "reason": "Running code is not switched on for this workspace yet."}
    pid, h = project_with(client, t, {"main.py": "print(1)"})
    r = client.post(f"/api/v1/projects/{pid}/run", json={"entry": "main.py"}, headers=h)
    assert r.status_code == 503 and "not switched on" in r.json()["detail"]


def test_enabled_without_runner_secret_stays_off(prepared_db, tokens, monkeypatch):
    monkeypatch.setenv("IDE_CODE_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IDE_RUNNER_URL", "https://runner.internal.test")
    monkeypatch.setenv("IDE_RUNNER_SECRET", "short")
    assert execution.status()["reason"] == "The code runner is not configured."


def test_runs_saved_project_files_and_audits(prepared_db, tokens, enabled, monkeypatch):
    sent = {}
    def fake(payload, client=None):
        sent.update(payload)
        return {"stdout": "42\n", "stderr": "", "exit_code": 0, "timed_out": False, "duration_ms": 12,
                "truncated": False, "runtime": "runsc", "language": "python"}
    monkeypatch.setattr(execution, "call_runner", fake)
    client = TestClient(main.app)
    pid, h = project_with(client, tokens(), {"src/main.py": "from util import X\nprint(X)", "src/util.py": "X = 42"})
    r = client.post(f"/api/v1/projects/{pid}/run", json={"entry": "src/main.py", "stdin": "abc"}, headers=h)
    assert r.status_code == 200 and r.json()["stdout"] == "42\n" and r.json()["exit_code"] == 0
    assert sent["entry"] == "src/main.py" and sent["language"] == "python" and sent["stdin"] == "abc"
    assert {f["path"] for f in sent["files"]} >= {"src/main.py", "src/util.py"}
    admin = create_engine(os.environ["IDE_TEST_ADMIN_DATABASE_URL"])
    with admin.connect() as db:
        row = db.execute(text("SELECT detail FROM ide_audit_events WHERE action='code.run' ORDER BY id DESC LIMIT 1")).first()
    admin.dispose()
    assert row and row[0].startswith("exit 0")


def test_rejects_unsaved_unsupported_and_read_only(prepared_db, tokens, enabled, monkeypatch):
    monkeypatch.setattr(execution, "call_runner", lambda *a, **k: pytest.fail("must not reach the runner"))
    client = TestClient(main.app)
    pid, h = project_with(client, tokens(), {"main.py": "print(1)", "run.sh": "ls"})
    assert client.post(f"/api/v1/projects/{pid}/run", json={"entry": "other.py"}, headers=h).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/run", json={"entry": "run.sh"}, headers=h).status_code == 400
    assert client.post(f"/api/v1/projects/{pid}/run", json={"entry": "../x.py"}, headers=h).status_code in (400, 404)
    viewer = headers(tokens("user-beta"), "beta")
    assert client.get("/api/v1/execution", headers=viewer).json()["reason"] == "Your role cannot run code."
    assert client.post(f"/api/v1/projects/{pid}/run", json={"entry": "main.py"}, headers=viewer).status_code == 403


def test_cannot_run_another_tenants_project(prepared_db, tokens, enabled, monkeypatch):
    monkeypatch.setattr(execution, "call_runner", lambda *a, **k: pytest.fail("must not reach the runner"))
    client = TestClient(main.app)
    pid, _ = project_with(client, tokens(), {"main.py": "print(1)"})
    other = headers(tokens("user-alpha"), "beta")  # member of beta, project belongs to alpha
    assert client.post(f"/api/v1/projects/{pid}/run", json={"entry": "main.py"}, headers=other).status_code in (403, 404)


def test_runner_url_must_be_tls_or_private(monkeypatch):
    monkeypatch.delenv("IDE_RUNNER_ALLOW_PRIVATE_HTTP", raising=False)
    assert execution.runner_url_ok("https://runner.example.test")
    assert execution.runner_url_ok("http://ide-runner:8080")
    assert not execution.runner_url_ok("http://10.0.1.5:8080")
    assert not execution.runner_url_ok("http://runner.example.test")
    monkeypatch.setenv("IDE_RUNNER_ALLOW_PRIVATE_HTTP", "true")
    assert execution.runner_url_ok("http://10.0.1.5:8080")
    assert not execution.runner_url_ok("http://203.0.113.9:8080")
    assert not execution.runner_url_ok("ftp://10.0.1.5")


def test_rate_limit(monkeypatch):
    monkeypatch.setenv("IDE_RUN_PER_MINUTE", "2"); execution._recent.clear()
    assert not execution.rate_limited("s", 0) and not execution.rate_limited("s", 1)
    assert execution.rate_limited("s", 2) and not execution.rate_limited("s", 61.5)


def test_runner_errors_are_honest(monkeypatch):
    monkeypatch.setenv("IDE_RUNNER_URL", "https://runner.internal.test"); monkeypatch.setenv("IDE_RUNNER_SECRET", SECRET)
    class Resp:
        def __init__(self, code): self.status_code, self.headers = code, {"content-type": "application/json"}
        def json(self): return {"detail": "bad entry"}
    from fastapi import HTTPException
    for code, expected in [(400, 400), (429, 429), (500, 503), (502, 503)]:
        with pytest.raises(HTTPException) as e:
            execution.call_runner({}, client=type("C", (), {"post": lambda self, *a, **k: Resp(code)})())
        assert e.value.status_code == expected
    with pytest.raises(HTTPException) as e:
        execution.call_runner({}, client=type("C", (), {"post": lambda self, *a, **k: (_ for _ in ()).throw(OSError())})())
    assert e.value.status_code == 503


# ------------------------------------------------------------------ full chain with a real container
IMAGE = os.getenv("RUNNER_TEST_IMAGE", "")
docker_ok = bool(IMAGE) and shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.skipif(not docker_ok, reason="needs Docker and RUNNER_TEST_IMAGE")
def test_full_chain_api_to_real_sandbox(prepared_db, tokens, enabled, monkeypatch):
    runner_dir = Path(__file__).resolve().parents[2] / "runner"
    sys.path.insert(0, str(runner_dir))  # for the runner's own "import sandbox"
    import importlib.util
    spec = importlib.util.spec_from_file_location("aepx_runner_app", runner_dir / "app.py")
    runner_app_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner_app_module)
    monkeypatch.setenv("RUNNER_SHARED_SECRET", SECRET)
    monkeypatch.setenv("RUNNER_IMAGE_PYTHON", IMAGE); monkeypatch.setenv("RUNNER_IMAGE_NODE", IMAGE)
    monkeypatch.setenv("RUNNER_RUNTIME", os.getenv("RUNNER_TEST_RUNTIME", "runc")); monkeypatch.setenv("RUNNER_ALLOW_RUNC", "true")
    runner = TestClient(runner_app_module.app, base_url="https://runner.internal.test")
    real_call = execution.call_runner
    monkeypatch.setattr(execution, "call_runner", lambda payload, client=None: real_call(payload, client=runner))
    client = TestClient(main.app)
    pid, h = project_with(client, tokens(), {"src/main.py": "import sys\nfrom util import X\nprint(X + 1)\nsys.exit(5)",
                                             "src/util.py": "X = 41", "web/app.js": "console.log('node', 6*7)"})
    r = client.post(f"/api/v1/projects/{pid}/run", json={"entry": "src/main.py"}, headers=h).json()
    assert r["stdout"].strip() == "42" and r["exit_code"] == 5 and r["timed_out"] is False
    r = client.post(f"/api/v1/projects/{pid}/run", json={"entry": "web/app.js"}, headers=h).json()
    assert r["stdout"].strip() == "node 42" and r["exit_code"] == 0
    # A tampered signature never reaches the sandbox.
    bad = runner.post("/run", content=b"{}", headers={"X-AEPX-Timestamp": "1", "X-AEPX-Signature": "0" * 64})
    assert bad.status_code == 401
