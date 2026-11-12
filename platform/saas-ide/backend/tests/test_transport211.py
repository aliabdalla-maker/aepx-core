"""No real credentials or external traffic: fail-closed transport checks."""
import pytest
from app.transport211 import approved_proxy_url,sdk_http_client,sdk_async_http_client
from app.providers import generate

def test_proxy_disabled_by_default(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        approved_proxy_url()

@pytest.mark.parametrize("proxy",[
    "http://gateway:8080","http://localhost:8080","http://gateway:3128",
    "http://gateway:8080@evil.invalid:8080","http://gateway:8080/redirect",
    "http://gateway:8080?target=169.254.169.254",
    "http://169.254.169.254:8080","http://gateway.evil.invalid:8080",
])
def test_proxy_bypass_denied(monkeypatch,proxy):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED","true")
    monkeypatch.setenv("IDE_NETWORK_ISOLATION_ATTESTED","true")
    monkeypatch.setenv("IDE_EGRESS_GATEWAY_VERIFIED","true")
    monkeypatch.setenv("IDE_EGRESS_CONNECT_PROXY",proxy)
    with pytest.raises(PermissionError):
        approved_proxy_url()

def test_sdk_transport_does_not_trust_ambient_proxy(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_NETWORK_ISOLATION_ATTESTED","IDE_EGRESS_GATEWAY_VERIFIED"):
        monkeypatch.setenv(key,"true")
    monkeypatch.setenv("IDE_EGRESS_CONNECT_PROXY","https://gateway:8080")
    monkeypatch.setenv("IDE_GATEWAY_TOKEN","x"*40)
    monkeypatch.setenv("IDE_GATEWAY_CA_FILE",__import__("certifi").where())
    monkeypatch.setenv("HTTPS_PROXY","http://evil.invalid:9000")
    with sdk_http_client() as client:
        assert client.follow_redirects is False
        assert client.trust_env is False if hasattr(client,"trust_env") else True
    import asyncio
    async def check():
        async with sdk_async_http_client() as client:
            assert client.follow_redirects is False
    asyncio.run(check())

def test_unintegrated_provider_fails_before_sdk(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_NETWORK_ISOLATION_ATTESTED","IDE_EGRESS_GATEWAY_VERIFIED"):
        monkeypatch.setenv(key,"true")
    monkeypatch.setenv("IDE_GEMINI_MODEL","mock-model")
    monkeypatch.setenv("GEMINI_API_KEY","test-not-real")
    with pytest.raises(PermissionError,match="not gateway-integrated"):
        generate("gemini","offline only")
