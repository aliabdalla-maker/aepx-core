"""Offline positive TLS-over-CONNECT integration.

Test-only gateway destination override routes provider.example to a loopback TLS
fixture. This is not an allowlist bypass in production: override is monkeypatch
scoped to this test process, and never exists in the deployed gateway.
"""
import datetime
import importlib.util
import ipaddress
import socket
import socketserver
import ssl
import threading
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

gateway_path=Path(__file__).resolve().parents[2]/"security"/"egress_gateway.py"
spec=importlib.util.spec_from_file_location("phase211_tls_gateway",gateway_path)
gateway=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

class MockTLSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        with self.server.tls_context.wrap_socket(self.request,server_side=True) as conn:
            conn.settimeout(5)
            payload=b""
            while b"\r\n\r\n" not in payload and len(payload)<8192:
                chunk=conn.recv(4096)
                if not chunk: return
                payload+=chunk
            self.server.requests_seen.append(payload.split(b"\r\n",1)[0])
            if b"/redirect" in payload.split(b"\r\n",1)[0]:
                conn.sendall(b"HTTP/1.1 302 Found\r\nLocation: https://169.254.169.254/secret\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            else:
                body=b'{"id":"mock-response","content":[{"type":"text","text":"offline"}]}'
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "+str(len(body)).encode()+b"\r\nConnection: close\r\n\r\n"+body)

@pytest.fixture
def tls_gateway(tmp_path,monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"provider.example")])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-datetime.timedelta(days=1))
          .not_valid_after(now+datetime.timedelta(days=1))
          .add_extension(x509.SubjectAlternativeName([x509.DNSName("provider.example")]),critical=False)
          .sign(key,hashes.SHA256()))
    cert_path=tmp_path/"mock.pem"
    key_path=tmp_path/"mock.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert_path),str(key_path))
    with socketserver.ThreadingTCPServer(("127.0.0.1",0),MockTLSHandler) as mock:
        mock.daemon_threads=True
        mock.tls_context=tls
        mock.requests_seen=[]
        thread=threading.Thread(target=mock.serve_forever,daemon=True)
        thread.start()
        original_create= gateway.socket.create_connection
        # Only the gateway's outbound connection to the test-only mock is rewritten.
        # The public hostname allowlist is still checked before this hook.
        monkeypatch.setattr(gateway,"permitted_destination",lambda authority,hosts: (
            "127.0.0.1" if authority=="provider.example:443" and "provider.example" in hosts
            else (_ for _ in ()).throw(PermissionError("Denied"))))
        def mock_connection(address,timeout=None,**kwargs):
            if address==("127.0.0.1",443):
                return original_create(("127.0.0.1",mock.server_address[1]),timeout=timeout,**kwargs)
            return original_create(address,timeout=timeout,**kwargs)
        monkeypatch.setattr(gateway.socket,"create_connection",mock_connection)
        monkeypatch.setenv("IDE_GATEWAY_TOKEN","t"*40)
        monkeypatch.setenv("IDE_GATEWAY_ALLOWED_HOSTS","provider.example")
        monkeypatch.setenv("IDE_GATEWAY_FORWARD_ENABLED","true")
        with gateway.Server(("127.0.0.1",0),gateway.Handler) as proxy:
            proxy_thread=threading.Thread(target=proxy.serve_forever,daemon=True)
            proxy_thread.start()
            try:
                yield f"http://127.0.0.1:{proxy.server_address[1]}",str(cert_path),mock.requests_seen
            finally:
                proxy.shutdown()
                proxy_thread.join(timeout=5)
        mock.shutdown()
        thread.join(timeout=5)

def test_authenticated_connect_verified_https_roundtrip(tls_gateway):
    proxy,cert,seen=tls_gateway
    with httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
                      verify=cert,trust_env=False,follow_redirects=False,timeout=5) as client:
        for path in ("/v1/responses","/v1/messages","/mcp"):
            response=client.get("https://provider.example"+path)
            assert response.status_code==200
            assert response.json()["id"]=="mock-response"
    assert len(seen)==3

def test_https_certificate_rejection(tls_gateway):
    proxy,cert,seen=tls_gateway
    with httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
                      verify=True,trust_env=False,timeout=5) as client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://provider.example/v1/messages")

def test_https_redirect_to_metadata_not_followed(tls_gateway):
    proxy,cert,seen=tls_gateway
    with httpx.Client(proxy=httpx.Proxy(proxy,headers={"Proxy-Authorization":"Bearer "+"t"*40}),
                      verify=cert,trust_env=False,follow_redirects=False,timeout=5) as client:
        response=client.get("https://provider.example/redirect")
        assert response.status_code==302
        assert response.headers["location"]=="https://169.254.169.254/secret"
    assert len(seen)==1
