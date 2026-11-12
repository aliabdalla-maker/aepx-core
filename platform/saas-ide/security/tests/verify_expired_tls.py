"""Offline regression: trusted-but-expired certificates must fail TLS validation.

Both gateway and upstream-provider TLS roles are tested with real handshakes.
No network outside the isolated test worker is used.
"""
import datetime as dt
import ipaddress
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
