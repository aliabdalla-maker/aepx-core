"""Fail-closed proxy configuration for explicitly approved SDK transports.

The proxy is an HTTP CONNECT endpoint on the worker's isolated Docker network.
TLS to providers remains end-to-end; network ACLs, not this module, must prevent
direct sockets. No provider traffic is enabled by importing this module.
"""
import os
from urllib.parse import urlsplit
import httpx

def approved_proxy_url() -> str:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true":
        raise PermissionError("External execution disabled")
    from .egress210 import assert_network_isolated
    assert_network_isolated()
    url=os.getenv("IDE_EGRESS_CONNECT_PROXY","")
    p=urlsplit(url)
    if (p.scheme!="http" or p.hostname!="gateway" or p.port!=8080 or
        p.path not in ("","/") or p.query or p.fragment or p.username or p.password):
        raise PermissionError("Dedicated isolated gateway required")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED")!="true":
        raise PermissionError("Gateway not verified")
    return url

def sdk_http_client():
    """Explicit httpx transport: no environment proxies or redirect following."""
    proxy=approved_proxy_url()
    token=os.getenv("IDE_GATEWAY_TOKEN","")
    if len(token)<32:
        raise PermissionError("Gateway credential missing")
    return httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+token}),
                        trust_env=False,follow_redirects=False,timeout=30)

def sdk_async_http_client():
    proxy=approved_proxy_url()
    token=os.getenv("IDE_GATEWAY_TOKEN","")
    if len(token)<32:
        raise PermissionError("Gateway credential missing")
    return httpx.AsyncClient(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+token}),
                             trust_env=False,follow_redirects=False,timeout=15)
