"""Phase 2.1 fail-closed tests; no external credentials or network required."""
import os
os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

import pytest
import asyncio
from app.providers import generate, configured_model
from app.worker import execute_one
from app.agent_runtime import invoke_mcp_tool, allowed_mcp_endpoint, approved_mcp_tool
from app.rag import embed, vector_literal

def test_all_external_adapters_disabled(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED", raising=False)
    with pytest.raises(PermissionError):
        generate("openai", "test")
    with pytest.raises(PermissionError):
        execute_one("alpha", "run")
    with pytest.raises(PermissionError):
        embed("hello")

def test_mcp_disabled(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED", raising=False)
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge", "search", {}))

def test_provider_explicit_credentials(monkeypatch):
    monkeypatch.delenv("IDE_OPENAI_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        configured_model("openai")
    with pytest.raises(ValueError):
        configured_model("not-provider")

def test_mcp_allowlist_and_https(monkeypatch):
    with pytest.raises(PermissionError):
        allowed_mcp_endpoint("untrusted")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "http://localhost:9000")
    with pytest.raises(RuntimeError):
        allowed_mcp_endpoint("knowledge")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_URL", "https://mcp.example.test/mcp")
    with pytest.raises(PermissionError):
        approved_mcp_tool("knowledge", "delete_all")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_TOOLS", "search,read")
    assert approved_mcp_tool("knowledge", "search") == "search"

def test_vector_input_rejection():
    with pytest.raises(ValueError):
        vector_literal([0.1])
    with pytest.raises(ValueError):
        vector_literal([float("nan")] * 1536)
