"""SC-01..12: bounds of the self-correction loop."""
import subprocess
import sys

import pytest

from conftest import PRODUCT

sys.path.insert(0, str(PRODUCT / "tools"))
import self_correct as sc  # noqa: E402

JUNIT = """<testsuite tests="2" failures="1"><testcase classname="t" name="ok"/>
<testcase classname="tests.test_x" name="test_restore"><failure message="RSP-04 restore without reason">
AssertionError password=hunter2 postgresql://aav:topsecret@db/aav Bearer abcdefghijklmnopqrstuvwxyz</failure></testcase></testsuite>"""


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=tmp_path, check=True)
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "junit.xml").write_text(JUNIT)
    return tmp_path


def test_observe_redacts_secrets_and_extracts_requirements(repo):
    f = sc.observe(str(repo / "junit.xml"))
    assert len(f) == 1 and f[0].requirement_ids == ["RSP-04"]
    assert "hunter2" not in f[0].message and "topsecret" not in f[0].message and "abcdefghijklmnop" not in f[0].message


def test_attempt_limit_then_escalation(repo, monkeypatch):
    monkeypatch.delenv("AAV_AEPX_BUS_URL", raising=False)
    b = sc.Budget(10_000, 1.0)
    for i in range(5):
        assert sc.correct(repo, str(repo / "junit.xml"), b)[0]["outcome"].startswith("diagnosis only")
    assert sc.correct(repo, str(repo / "junit.xml"), b)[0]["outcome"].startswith("escalated")


def test_budget_cap_and_no_recursion(repo, monkeypatch):
    b = sc.Budget(100, 1.0)
    with pytest.raises(RuntimeError):
        b.reserve(101, 0)
    monkeypatch.setenv("AAV_SELFCORRECT_ACTIVE", "1")
    with pytest.raises(RuntimeError):
        sc.correct(repo, str(repo / "junit.xml"), sc.Budget(1000, 1))


def test_only_verified_learning_and_no_merge_path(repo):
    led = sc.Ledger(repo)
    with pytest.raises(ValueError):
        led.learn({"verified": False})
    src = (PRODUCT / "tools" / "self_correct.py").read_text()
    assert "gh pr merge" not in src and "--draft" in src and "deploy" not in src.split('"""', 2)[2].lower()
