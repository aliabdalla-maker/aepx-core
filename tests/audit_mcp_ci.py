"""Fail-closed audit of MCP CI trigger and test coverage; stdlib only."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/mcp-offline-contract.yml"
BACKEND=ROOT/"platform/saas-ide/backend/app"
TESTS=ROOT/"tests"

def audit():
    content=WORKFLOW.read_text(encoding="utf-8")
    try:
        pr=content.split("  pull_request:\n",1)[1].split("  push:\n",1)[0]
        push=content.split("  push:\n",1)[1].split("  workflow_dispatch:",1)[0]
    except IndexError as exc:
        raise AssertionError("MCP CI trigger blocks missing") from exc
    quoted=re.compile(r"^\s+- '([^']+)'\s*$",re.M)
    pr_paths=set(quoted.findall(pr))
    push_paths=set(quoted.findall(push))
    assert pr_paths and pr_paths==push_paths, (
        "MCP CI pull-request and master-push filters diverged: "
        f"PR-only={sorted(pr_paths-push_paths)}, push-only={sorted(push_paths-pr_paths)}")
    assert "branches: [master]" in push, "master push must trigger MCP CI"
    assert "python -m compileall -q platform/saas-ide/backend/app" in content, (
        "backend compilation gate missing")
    sources={p.relative_to(ROOT).as_posix() for p in BACKEND.glob("mcp_*.py")}
    tests={p.relative_to(ROOT).as_posix() for p in TESTS.glob("test_mcp_*.py")}
    missing=(sources|tests)-pr_paths
    assert not missing, f"MCP CI trigger paths missing: {sorted(missing)}"
    untested=[]
    for test in sorted(tests):
        pattern=Path(test).name
        if f"-p '{pattern}'" not in content:
            untested.append(pattern)
    assert not untested, f"MCP tests not executed in workflow: {untested}"
    assert ".github/workflows/mcp-offline-contract.yml" in pr_paths
    assert "python tests/audit_mcp_ci.py" in content, "self-audit must execute"
    print(f"MCP CI audit passed: {len(sources)} modules, {len(tests)} test files")

if __name__=="__main__":
    try:
        audit()
    except (AssertionError,OSError) as exc:
        print(f"MCP CI audit FAILED: {exc}",file=sys.stderr)
        raise SystemExit(1)
