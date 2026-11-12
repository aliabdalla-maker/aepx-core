"""Test-only pinned-IP HTTPS gateway: DNS is checked immediately before socket creation.

No redirects, proxies, ambient credentials, or arbitrary HTTP methods. This is a
test harness, not a substitute for an OS-enforced production outbound firewall.
"""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit
from .egress25 import validate_https_destination

def resolve_public(host: str, *, resolver=socket.getaddrinfo) -> str:
    addresses=resolver(host,443,type=socket.SOCK_STREAM)
    if not addresses:
        raise PermissionError("DNS returned no addresses")
    ips={entry[4][0] for entry in addresses}
    if any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise PermissionError("DNS returned a nonpublic address")
    if len(ips)!=1:
        # Avoid nondeterministic address selection; explicitly pin one audited IP.
        raise PermissionError("Ambiguous DNS resolution")
    return ips.pop()

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_ip: str, *, timeout: float=3):
        super().__init__(host,port=443,timeout=timeout,context=ssl.create_default_context())
        if not ipaddress.ip_address(pinned_ip).is_global:
            raise PermissionError("Pinned address must be globally routable")
        self.pinned_ip=pinned_ip

    def connect(self):
        # Never resolve the hostname again at the connection boundary.
        raw=socket.create_connection((self.pinned_ip,443),self.timeout)
        try:
            self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close()
            raise

def gateway_get(url: str, *, allowed_hosts: set[str], resolver=socket.getaddrinfo) -> bytes:
    validate_https_destination(url,allowed_hosts=allowed_hosts)
    parsed=urlsplit(url)
    if parsed.port not in (None,443):
        raise PermissionError("Only HTTPS 443 allowed")
    ip=resolve_public(parsed.hostname,resolver=resolver)
    connection=PinnedHTTPSConnection(parsed.hostname,ip)
    try:
        connection.request("GET",(parsed.path or "/")+("?"+parsed.query if parsed.query else ""),
                           headers={"Host":parsed.hostname,"Connection":"close"})
        response=connection.getresponse()
        if response.status in (301,302,303,307,308):
            raise PermissionError("Redirects forbidden")
        if response.status!=200:
            raise RuntimeError("Gateway request failed")
        data=response.read(1024*1024+1)
        if len(data)>1024*1024:
            raise PermissionError("Response size exceeded")
        return data
    finally:
        connection.close()
