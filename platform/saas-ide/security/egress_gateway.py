"""Restricted HTTPS CONNECT gateway. Experimental, disabled by default.

Run only in a dedicated dual-homed gateway container with independent network
policy. Does not terminate TLS; clients verify provider certificates themselves.
No HTTP forwarding, DNS tunnelling, arbitrary ports, or authentication fallback.
"""
import ipaddress
import hmac
import os
import select
import socket
import socketserver
import ssl

def permitted_destination(authority, hosts, resolver=socket.getaddrinfo):
    if not isinstance(authority,str) or authority.count(":")!=1:
        raise PermissionError("Invalid CONNECT authority")
    host,port=authority.rsplit(":",1)
    if not host or host.endswith(".") or host.lower()!=host or port!="443":
        raise PermissionError("Canonical HTTPS host:443 required")
    if host not in hosts or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host):
        raise PermissionError("Host not allowlisted")
    if host.startswith("-") or ".." in host:
        raise PermissionError("Malformed hostname")
    answers=resolver(host,443,type=socket.SOCK_STREAM)
    ips={item[4][0] for item in answers}
    if len(ips)!=1 or any((not ipaddress.ip_address(ip).is_global) or ipaddress.ip_address(ip).is_multicast for ip in ips):
        raise PermissionError("DNS not pinned to a single public address")
    return next(iter(ips))

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        try:
            first=b""
            while b"\r\n\r\n" not in first and len(first)<8192:
                data=self.request.recv(1024)
                if not data: return
                first+=data
            if b"\r\n\r\n" not in first or len(first)>8192: return
            header,rest=first.split(b"\r\n\r\n",1)
            lines=header.split(b"\r\n")
            method,authority,version=lines[0].decode("ascii").split(" ")
            if method!="CONNECT" or version!="HTTP/1.1" or rest:
                raise PermissionError("Only CONNECT permitted")
            # Reject Proxy-Authorization and other unreviewed headers. A gateway
            # credential is checked against a separately mounted secret.
            headers={}
            for line in lines[1:]:
                key,sep,value=line.partition(b":")
                if not sep or key.lower() in headers:
                    raise PermissionError("Malformed proxy headers")
                headers[key.lower()]=value.strip()
            token=os.environ.get("IDE_GATEWAY_TOKEN","")
            if len(token)<32 or not hmac.compare_digest(headers.get(b"proxy-authorization",b""),("Bearer "+token).encode()):
                raise PermissionError("Gateway authorization required")
            hosts={x for x in os.environ.get("IDE_GATEWAY_ALLOWED_HOSTS","").split(",") if x}
            ip=permitted_destination(authority,hosts)
            if os.environ.get("IDE_GATEWAY_FORWARD_ENABLED")!="true":
                raise PermissionError("Forwarding disabled")
            upstream=socket.create_connection((ip,443),timeout=5)
            try:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.request.settimeout(None)
                upstream.settimeout(None)
                sockets=[self.request,upstream]
                while True:
                    # TLS ingress may have decrypted application bytes buffered
                    # internally even when its underlying fd is not readable.
                    # Drain them before waiting on select, otherwise a CONNECT
                    # followed by nested provider TLS can deadlock.
                    ready=[self.request] if self.request.pending() else []
                    if not ready:
                        ready,_,_=select.select(sockets,[],[],30)
                    if not ready: break
                    for sock in ready:
                        chunk=sock.recv(65536)
                        if not chunk: return
                        (upstream if sock is self.request else self.request).sendall(chunk)
            finally:
                upstream.close()
        except (OSError,ValueError,PermissionError,UnicodeError):
            try: self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError: pass

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

class TLSServer(Server):
    """Require encrypted gateway ingress independently of upstream provider TLS."""
    def __init__(self, address, handler, context):
        self.tls_context=context
        super().__init__(address,handler)

    def get_request(self):
        conn,addr=super().get_request()
        try:
            return self.tls_context.wrap_socket(conn,server_side=True),addr
        except Exception:
            conn.close()
            raise

def gateway_tls_context():
    cert=os.getenv("IDE_GATEWAY_TLS_CERT_FILE","")
    key=os.getenv("IDE_GATEWAY_TLS_KEY_FILE","")
    if not cert or not key:
        raise RuntimeError("Gateway TLS certificate and key required")
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert,key)
    return ctx

if __name__=="__main__":
    if os.environ.get("IDE_GATEWAY_LISTEN_ENABLED")!="true":
        raise SystemExit("Gateway disabled")
    with TLSServer(("0.0.0.0",8080),Handler,gateway_tls_context()) as server:
        server.serve_forever()
