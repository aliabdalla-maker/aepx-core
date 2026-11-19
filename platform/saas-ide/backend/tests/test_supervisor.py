"""Unit tests for Phase 2 governance and routing without external API credentials."""
import os
os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

import pytest
from app.supervisor import plan_steps, route_model
from app.agent_runtime import allowed_mcp_endpoint, execute_crewai_plan

def test_plan_has_review_gate():
    steps = plan_steps("Build an application")
    assert len(steps) == 4
    assert steps[-1]["agent"] == "verifier"
    assert not any(step["action"] == "execute" for step in steps)

def test_provider_fail_closed(monkeypatch):
    for name in ("OCI", "OPENAI", "ANTHROPIC", "GEMINI"):
        monkeypatch.delenv("IDE_LLM_" + name + "_ENABLED", raising=False)
    assert route_model() == "unconfigured"
    with pytest.raises(ValueError):
        route_model("openai")
    monkeypatch.setenv("IDE_LLM_OCI_ENABLED", "true")
    assert route_model() == "oci"
    assert route_model("oci") == "oci"

def test_mcp_allowlist(monkeypatch):
    with pytest.raises(PermissionError):
        allowed_mcp_endpoint("arbitrary")
    with pytest.raises(RuntimeError):
        allowed_mcp_endpoint("knowledge")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://mcp.example.test/mcp")
    assert allowed_mcp_endpoint("knowledge").startswith("https://")

def test_crewai_disabled_by_default(monkeypatch):
    monkeypatch.delenv("IDE_CREWAI_EXECUTION_ENABLED", raising=False)
    with pytest.raises(PermissionError):
        execute_crewai_plan("do something", "unconfigured")
