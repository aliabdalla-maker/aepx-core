"""Fail-closed MCP authorization checks. No external network or DB connections."""
import asyncio
import os

import pytest

os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

from app import agent_runtime, egress210


def invoke(**kwargs):
    return asyncio.run(agent_runtime.invoke_mcp_tool(
        "knowledge", "read", {"query": "offline"}, **kwargs))


def test_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED", raising=False)
    monkeypatch.delenv("IDE_MCP_EXECUTION_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="disabled"):
        invoke(db=object(), tenant_id="tenant-a", run_id="run-a")


def test_mcp_requires_both_execution_flags(monkeypatch):
    for external, mcp in (("true", "false"), ("false", "true")):
        monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED", external)
        monkeypatch.setenv("IDE_MCP_EXECUTION_ENABLED", mcp)
        with pytest.raises(PermissionError, match="disabled"):
            invoke(db=object(), tenant_id="tenant-a", run_id="run-a")


def test_mcp_rejects_unapproved_server_and_tool(monkeypatch):
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://provider.example/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS", "read")
    with pytest.raises(PermissionError, match="not approved"):
        agent_runtime.allowed_mcp_endpoint("unapproved")
    with pytest.raises(PermissionError, match="not allowlisted"):
        agent_runtime.approved_mcp_tool("knowledge", "delete")
    assert agent_runtime.approved_mcp_tool("knowledge", "read") == "read"


def test_mcp_requires_tenant_and_run_before_transport(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IDE_MCP_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://provider.example/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS", "read")
    monkeypatch.setattr(egress210, "assert_network_isolated", lambda: None)
    for context in (
        {"db": None, "tenant_id": "tenant-a", "run_id": "run-a"},
        {"db": object(), "tenant_id": None, "run_id": "run-a"},
        {"db": object(), "tenant_id": "tenant-a", "run_id": None},
    ):
        with pytest.raises(PermissionError, match="Tenant-bound"):
            invoke(**context)


def test_mcp_rejects_oversized_arguments_before_transport(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("IDE_MCP_EXECUTION_ENABLED", "true")
    monkeypatch.setattr(egress210, "assert_network_isolated", lambda: None)
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(agent_runtime.invoke_mcp_tool(
            "knowledge", "read", {"payload": "x" * 4100},
            db=object(), tenant_id="tenant-a", run_id="run-a"))
