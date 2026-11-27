"""Release and deployment tooling (Phase 1/2 of the implementation plan): version reporting, the post-deploy
smoke test against a real running control plane (RA-03, RA-11, REL-01, FN-06)."""
from __future__ import annotations

import importlib.util
import socket
import threading
import time

import pytest

from conftest import PRODUCT


def _load(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


smoke = _load("smoke_release", PRODUCT / "tools" / "smoke_release.py")


def test_health_reports_version_build_and_environment(client):
    from app.main import app
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == app.version == "0.1.2"
    assert {"build", "environment"} <= body.keys()


@pytest.fixture(scope="module")
def live_api(client, baseline_bundle):
    import uvicorn
    from app.main import app
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=10)


def test_smoke_tool_passes_against_running_control_plane(live_api):
    run = smoke.Run()
    smoke.check_api(run, live_api, "0.1.2", None)
    failed = [c for c in run.checks if not c["passed"]]
    assert not failed, failed
    names = {c["check"] for c in run.checks}
    assert {"health 200", "version", "ready", "detection bundle published", "protected route needs auth"} <= names


def test_smoke_tool_fails_on_wrong_version_and_unreachable_host(live_api):
    run = smoke.Run()
    smoke.check_api(run, live_api, "9.9.9", None)
    assert not run.passed
    assert [c["check"] for c in run.checks if not c["passed"]] == ["version"]
    down = smoke.Run()
    smoke.check_api(down, "http://127.0.0.1:9", "0.1.2", None)
    assert not down.passed and "unreachable" in down.checks[0]["detail"]


def test_load_test_tool_runs_a_small_fleet(live_api, new_account):
    """NFR-02 tooling: the same tool that runs the 1,000-endpoint test, at small scale against a real control plane."""
    import argparse
    import asyncio
    load = _load("load_test", PRODUCT / "tools" / "load_test.py")
    admin = new_account("load")
    if not admin.get("/v1/policies").json():
        admin.post("/v1/policies", json={"name": "default", "body": {"on_access": True, "on_execute": True}})
    tok = admin.post("/v1/enrollment-tokens", json={"max_uses": 25}).json()["token"]
    a = argparse.Namespace(api=live_api, token=tok, agents=20, minutes=0.05, interval=1, events=5, backlog=20,
                           connections=20, max_heartbeat_p95=5000, max_events_p95=10000, max_error_rate=0.01)
    res = asyncio.run(load.main_async(a))
    assert res["enrolled"] == 20 and res["passed"], res
    assert res["operations"]["heartbeat"]["requests"] >= 20 and res["operations"]["reconnect_events"]["errors"] == 0
