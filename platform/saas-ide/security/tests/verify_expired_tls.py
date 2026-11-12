"""Offline regression: trusted-but-expired certificates must fail TLS validation.

Both gateway and upstream-provider TLS roles are tested with real handshakes.
No network outside the isolated test worker is used.
"""
import datetime as dt
import socket
import ssl
import tempfile
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

def certificate(hostname):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=30))
        .not_valid_after(now - dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return (cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()))

def check_role(role):
    hostname = "gateway" if role == "gateway" else "provider.example"
    with tempfile.TemporaryDirectory() as directory:
        crt, key = certificate(hostname)
        cert_path = Path(directory) / "expired.crt"
        key_path = Path(directory) / "expired.key"
        cert_path.write_bytes(crt)
        key_path.write_bytes(key)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(cert_path), str(key_path))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        errors = []
        def serve():
            try:
                conn, _ = listener.accept()
                with conn:
                    try:
                        with server_context.wrap_socket(conn, server_side=True):
                            pass
                    except ssl.SSLError:
                        pass  # Expected: client rejects the expired certificate.
            except Exception as exc:
                errors.append(exc)
            finally:
                listener.close()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client_context = ssl.create_default_context(cafile=str(cert_path))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with client_context.wrap_socket(raw, server_hostname=hostname):
                    raise AssertionError(f"Expired {role} certificate was accepted")
        except ssl.SSLCertVerificationError as exc:
            assert "expired" in str(exc).lower(), str(exc)
        thread.join(timeout=5)
        assert not thread.is_alive(), "TLS fixture did not terminate"
        assert not errors, errors
        print(f"Expired {role} TLS certificate rejected with trusted certificate authority")

for role in ("gateway", "provider"):
    check_role(role)

# End-to-end ingress acceptance: run the real gateway TLS listener and
# reject its expired certificate before any CONNECT request is sent.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "production_gateway", "/opt/gateway/egress_gateway.py")
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
with tempfile.TemporaryDirectory() as directory:
    crt, key = certificate("gateway")
    cert_path = Path(directory) / "gateway.crt"
    key_path = Path(directory) / "gateway.key"
    cert_path.write_bytes(crt)
    key_path.write_bytes(key)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(cert_path), str(key_path))
    with gateway.TLSServer(("127.0.0.1", 0), gateway.Handler, server_context) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            trusted = ssl.create_default_context(cafile=str(cert_path))
            try:
                with socket.create_connection(server.server_address, timeout=5) as raw:
                    with trusted.wrap_socket(raw, server_hostname="gateway"):
                        raise AssertionError("Real gateway accepted expired ingress TLS")
            except ssl.SSLCertVerificationError as exc:
                assert "expired" in str(exc).lower(), str(exc)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive(), "Gateway fixture did not stop"
print("Real gateway listener rejects expired ingress TLS certificate")


# End-to-end upstream acceptance: the production CONNECT handler forwards
# opaque bytes to an expired synthetic provider; HTTPX must reject provider TLS.
# Only loopback sockets are used. The production destination policy is overridden
# in this test process alone, never in deployed configuration.
import httpx
with tempfile.TemporaryDirectory() as directory:
    crt, key = certificate("provider.example")
    cert_path = Path(directory) / "expired-provider.crt"
    key_path = Path(directory) / "expired-provider.key"
    cert_path.write_bytes(crt)
    key_path.write_bytes(key)
    upstream_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    upstream_context.load_cert_chain(str(cert_path), str(key_path))
    provider_listener = socket.socket()
    provider_listener.bind(("127.0.0.1", 0))
    provider_listener.listen(1)
    upstream_port = provider_listener.getsockname()[1]
    provider_errors = []
    def serve_expired_provider():
        try:
            conn, _ = provider_listener.accept()
            with conn:
                try:
                    with upstream_context.wrap_socket(conn, server_side=True):
                        pass
                except ssl.SSLError:
                    pass  # Expected certificate rejection by the client.
        except Exception as exc:
            provider_errors.append(exc)
        finally:
            provider_listener.close()
    provider_thread = threading.Thread(target=serve_expired_provider, daemon=True)
    provider_thread.start()

    gateway_crt, gateway_key = certificate("gateway")
    # Gateway ingress must remain valid so that rejection is attributable to
    # upstream provider expiry alone. Use a separately issued valid fixture.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    now = dt.datetime.now(dt.timezone.utc)
    gateway_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    gateway_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "gateway")])
    gateway_cert = (x509.CertificateBuilder().subject_name(gateway_name)
        .issuer_name(gateway_name).public_key(gateway_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("gateway")]), critical=False)
        .sign(gateway_private_key, hashes.SHA256()))
    gateway_cert_path = Path(directory) / "valid-gateway.crt"
    gateway_key_path = Path(directory) / "valid-gateway.key"
    gateway_cert_path.write_bytes(gateway_cert.public_bytes(serialization.Encoding.PEM))
    gateway_key_path.write_bytes(gateway_private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    ingress_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ingress_context.load_cert_chain(str(gateway_cert_path), str(gateway_key_path))
    real_create_connection = socket.create_connection
    real_destination_policy = gateway.permitted_destination
    def test_destination(authority, hosts, resolver=socket.getaddrinfo):
        if authority != "provider.example:443":
            raise PermissionError("Test-only destination allowlist")
        return "127.0.0.1"
    def test_upstream_connection(address, timeout=None, source_address=None, **kwargs):
        if address == ("127.0.0.1", 443):
            return real_create_connection(("127.0.0.1", upstream_port), timeout,
                                          source_address, **kwargs)
        return real_create_connection(address, timeout, source_address, **kwargs)
    gateway.permitted_destination = test_destination
    gateway.socket.create_connection = test_upstream_connection
    import os
    original_token = os.environ.get("IDE_GATEWAY_TOKEN")
    original_hosts = os.environ.get("IDE_GATEWAY_ALLOWED_HOSTS")
    original_forward = os.environ.get("IDE_GATEWAY_FORWARD_ENABLED")
    test_token = "offline-expired-certificate-test-token-1234567890"
    os.environ.update(IDE_GATEWAY_TOKEN=test_token,
                      IDE_GATEWAY_ALLOWED_HOSTS="provider.example",
                      IDE_GATEWAY_FORWARD_ENABLED="true")
    try:
        with gateway.TLSServer(("127.0.0.1", 0), gateway.Handler, ingress_context) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                proxy_context = ssl.create_default_context(cafile=str(gateway_cert_path))
                provider_context = ssl.create_default_context(cafile=str(cert_path))
                with httpx.Client(
                    proxy=httpx.Proxy(
                        f"https://127.0.0.1:{server.server_address[1]}",
                        ssl_context=proxy_context,
                        headers={"Proxy-Authorization":"Bearer "+test_token}),
                    verify=provider_context, trust_env=False, timeout=5) as client:
                    try:
                        client.get("https://provider.example/")
                    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                        assert "CERTIFICATE_VERIFY_FAILED" in str(exc), str(exc)
                        assert "expired" in str(exc).lower(), str(exc)
                    else:
                        raise AssertionError("Expired upstream TLS accepted via CONNECT")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                assert not thread.is_alive()
    finally:
        gateway.permitted_destination = real_destination_policy
        gateway.socket.create_connection = real_create_connection
        for name, value in (
            ("IDE_GATEWAY_TOKEN", original_token),
            ("IDE_GATEWAY_ALLOWED_HOSTS", original_hosts),
            ("IDE_GATEWAY_FORWARD_ENABLED", original_forward),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    provider_thread.join(timeout=5)
    assert not provider_thread.is_alive(), "Expired provider fixture did not terminate"
    assert not provider_errors, provider_errors
print("End-to-end authenticated CONNECT rejected trusted expired upstream provider TLS")
