"""Offline gateway handler acceptance with simulated rebinding DNS answers.

The real TLS listener and production destination policy are exercised. Resolver
answers are injected only in this isolated test process; no outbound sockets.
"""
import importlib.util
import os
import socket
import ssl
import threading

spec = importlib.util.spec_from_file_location("gateway", "/opt/gateway/egress_gateway.py")
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

original_policy = gateway.permitted_destination
original_connect = gateway.socket.create_connection
token = "offline-dns-rebinding-test-token-1234567890"
os.environ["IDE_GATEWAY_TOKEN"] = token
os.environ["IDE_GATEWAY_ALLOWED_HOSTS"] = "provider.example"
os.environ["IDE_GATEWAY_FORWARD_ENABLED"] = "true"

attempted_connections = []
def forbidden_upstream(*args, **kwargs):
    attempted_connections.append((args, kwargs))
    raise AssertionError("Upstream socket attempted for rebinding DNS response")

gateway.socket.create_connection = forbidden_upstream
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/certs/gateway.crt", "/certs/gateway.key")

def resolve_to(*ips):
    def resolver(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
    return resolver

def request_gateway(port):
    # Preserve the real socket constructor; the test only traps gateway upstream calls.
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(5)
    raw.connect(("127.0.0.1", port))
    with ssl.create_default_context(cafile="/certs/gateway.crt").wrap_socket(
        raw, server_hostname="gateway") as tls:
        tls.settimeout(5)
        tls.sendall(("CONNECT provider.example:443 HTTP/1.1\r\n"
                     "Proxy-Authorization: Bearer " + token + "\r\n\r\n").encode())
        return tls.recv(4096)

try:
    with gateway.TLSServer(("127.0.0.1", 0), gateway.Handler, context) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for answers in (
                ("203.0.113.10", "127.0.0.1"),
                ("203.0.113.10", "169.254.169.254"),
                ("127.0.0.1",),
                ("169.254.169.254",),
                ("10.0.0.5",),
            ):
                gateway.permitted_destination = (
                    lambda authority, hosts, ips=answers:
                    original_policy(authority, hosts, resolver=resolve_to(*ips))
                )
                response = request_gateway(server.server_address[1])
                assert response.startswith(b"HTTP/1.1 403"), (answers, response)
                assert not attempted_connections, attempted_connections
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive(), "Test gateway failed to stop"
finally:
    gateway.permitted_destination = original_policy
    gateway.socket.create_connection = original_connect
print("Real gateway handler denied rebinding/private DNS before upstream connection")
