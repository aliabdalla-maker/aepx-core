"""Actual offline HTTP CONNECT wire tests against the default-deny gateway.

No live providers, credentials or network forwarding. Positive TLS/provider SDK
integration is intentionally NOT claimed by these denial-path tests.
"""
import importlib.util
import socket
import threading
from pathlib import Path

import httpx
import pytest

path=Path(__file__).resolve().parents[2]/"security"/"egress_gateway.py"
spec=importlib.util.spec_from_file_location("phase211_gateway_wire",path)
gateway=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

@pytest.fixture
def gateway_server(monkeypatch):
    monkeypatch.setenv("IDE_GATEWAY_TOKEN","a"*40)
    monkeypatch.setenv("IDE_GATEWAY_FORWARD_ENABLED","false")
    monkeypatch.setenv("IDE_GATEWAY_ALLOWED_HOSTS","provider.example")
    with gateway.Server(("127.0.0.1",0),gateway.Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        yield server.server_address[1]
        server.shutdown()
        thread.join(timeout=5)

@pytest.mark.parametrize("request",[
    b"GET http://provider.example/ HTTP/1.1\r\nHost: provider.example\r\n\r\n",
    b"CONNECT 169.254.169.254:443 HTTP/1.1\r\nProxy-Authorization: Bearer "+b"a"*40+b"\r\n\r\n",
    b"CONNECT provider.example:80 HTTP/1.1\r\nProxy-Authorization: Bearer "+b"a"*40+b"\r\n\r\n",
    b"CONNECT provider.example:443 HTTP/1.1\r\nProxy-Authorization: Bearer invalid\r\n\r\n",
    b"CONNECT provider.example:443 HTTP/1.1\r\nProxy-Authorization: Bearer "+b"a"*40+b"\r\nProxy-Authorization: Bearer "+b"a"*40+b"\r\n\r\n",
])
def test_gateway_denies_wire_bypasses(gateway_server,request):
    with socket.create_connection(("127.0.0.1",gateway_server),timeout=2) as conn:
        conn.sendall(request)
        assert conn.recv(256).startswith(b"HTTP/1.1 403")

def test_httpx_real_connect_denied_without_proxy_credential(gateway_server):
    with httpx.Client(proxy=f"http://127.0.0.1:{gateway_server}",trust_env=False,
                      follow_redirects=False,timeout=3) as client:
        with pytest.raises(httpx.ProxyError):
            client.get("https://provider.example/v1/messages")

def test_gateway_does_not_follow_redirect_or_forward(gateway_server):
    with socket.create_connection(("127.0.0.1",gateway_server),timeout=2) as conn:
        conn.sendall(b"CONNECT provider.example:443 HTTP/1.1\r\nProxy-Authorization: Bearer "+b"a"*40+b"\r\n\r\n")
        assert conn.recv(256).startswith(b"HTTP/1.1 403")
