"""Fail-closed proxy configuration for explicitly approved SDK transports.

The proxy is an HTTP CONNECT endpoint on the worker's isolated Docker network.
TLS to providers remains end-to-end; network ACLs, not this module, must prevent
direct sockets. No provider traffic is enabled by importing this module.
"""
import os
import ssl
from urllib.parse import urlsplit
import httpx

def approved_proxy_url() -> str:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true":
        raise PermissionError("External execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    url=os.getenv("IDE_EGRESS_CONNECT_PROXY","")
    p=urlsplit(url)
    if (p.scheme!="https" or p.hostname!="gateway" or p.port!=8080 or
        p.path not in ("","/") or p.query or p.fragment or p.username or p.password):
        raise PermissionError("Dedicated isolated gateway required")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED")!="true":
        raise PermissionError("Gateway not verified")
    return url

def authenticated_proxy():
    url=approved_proxy_url()
    token=os.getenv("IDE_GATEWAY_TOKEN","")
    ca=os.getenv("IDE_GATEWAY_CA_FILE","")
    if len(token)<32 or not ca or not os.path.isfile(ca):
        raise PermissionError("Gateway credential or CA trust anchor missing")
    ctx=ssl.create_default_context(cafile=ca)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    return httpx.Proxy(url,headers={"Proxy-Authorization":"Bearer "+token},ssl_context=ctx)

def sdk_http_client():
    """Explicit httpx transport: no environment proxies or redirect following."""
    return httpx.Client(proxy=authenticated_proxy(),
                        trust_env=False,follow_redirects=False,timeout=30)

def sdk_async_http_client():
    return httpx.AsyncClient(proxy=authenticated_proxy(),
                             trust_env=False,follow_redirects=False,timeout=15)
