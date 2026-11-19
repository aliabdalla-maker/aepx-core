"""Phase 2.10 fail-closed preflight regressions. No network requests."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import pytest
from app.egress210 import assert_network_isolated,approved_destination
from app.providers import generate
from app.agent_runtime import invoke_mcp_tool

def dns(ip):
    return lambda *a,**kw: [(2,1,6,"",(ip,443))]

@pytest.mark.parametrize("url",[
    "http://provider.example.test/","https://127.0.0.1/",
    "https://169.254.169.254/","https://provider.example.test:8443/",
    "https://provider.example.test.evil.invalid/",
    "https://user@provider.example.test/",
    "https://provider.example.test./",
])
def test_ssrf_and_url_bypass_rejected(url):
    with pytest.raises((PermissionError,ValueError)):
        approved_destination(url,allowed_hosts={"provider.example.test"},resolver=dns("8.8.8.8"))

def test_dns_rebinding_rejected():
    with pytest.raises(PermissionError):
        approved_destination("https://provider.example.test/",
                             allowed_hosts={"provider.example.test"},resolver=dns("10.0.0.4"))

def test_pinned_destination_passes_public_ip_only():
    assert approved_destination("https://provider.example.test/",
        allowed_hosts={"provider.example.test"},resolver=dns("8.8.8.8"))==("provider.example.test","8.8.8.8")

def test_network_attestation_required_even_if_execution_flag_enabled(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED","true")
    monkeypatch.setenv("IDE_EGRESS_GATEWAY_VERIFIED","true")
    monkeypatch.delenv("IDE_NETWORK_ISOLATION_ATTESTED",raising=False)
    with pytest.raises(PermissionError):
        assert_network_isolated()
    with pytest.raises(PermissionError):
        generate("openai","never send")
    import asyncio
    monkeypatch.setenv("IDE_MCP_EXECUTION_ENABLED","true")
    with pytest.raises(PermissionError):
        asyncio.run(invoke_mcp_tool("knowledge","search",{"q":"never send"}))
