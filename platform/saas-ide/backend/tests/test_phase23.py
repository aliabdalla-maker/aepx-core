"""Adversarial fail-closed and budget tests without external network."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import asyncio
import pytest
from app.agent_runtime import invoke_mcp_tool
from app.timeout23 import hard_deadline
from app.phase23 import reserve_budget, fenced_claim

def test_external_execution_disabled(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        hard_deadline(str,"hello")
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge","search",{},db=object(),tenant_id="alpha",run_id="r"))

def test_mcp_cannot_bypass_approval_or_proxy(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED","true")
    monkeypatch.setenv("IDE_MCP_EXECUTION_ENABLED","true")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL","https://mcp.example.test/mcp")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS","search")
    monkeypatch.delenv("IDE_MCP_EGRESS_PROXY",raising=False)
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge","search",{"q":"x"}))
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge","search",{"q":"x"},db=object(),tenant_id="alpha",run_id="r"))

def test_deadline_bounds(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED","true")
    with pytest.raises(ValueError):
        hard_deadline(str,"x",seconds=0)
    with pytest.raises(ValueError):
        hard_deadline(str,"x",seconds=61)
