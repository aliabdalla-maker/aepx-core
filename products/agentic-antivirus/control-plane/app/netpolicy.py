"""Outbound network policy (AX-16 deny-by-default egress, INT-08, INT-09 SSRF defence)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings

ALLOWED_SCHEMES = {"https", "sftp", "imaps", "smtps", "amqps", "mqtts", "grpcs", "postgresql"}


class EgressDenied(Exception):
    pass


def check_endpoint(url: str, *, allow_private: bool = False, resolver=socket.getaddrinfo) -> dict:
    """Validate an outbound endpoint. Raises EgressDenied. TLS-only schemes; host must be on
    the configured allowlist; every resolved address must be public unless the integration is
    an approved private-network endpoint."""
    u = urlparse(url)
    if u.scheme not in ALLOWED_SCHEMES:
        raise EgressDenied(f"scheme '{u.scheme}' not allowed (TLS required)")
    host = (u.hostname or "").lower().rstrip(".")
    if not host:
        raise EgressDenied("no host")
    if not any(host == d or host.endswith("." + d) for d in settings.egress_allowlist):
        raise EgressDenied(f"host '{host}' not on egress allowlist")
    try:
        infos = resolver(host, u.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise EgressDenied(f"cannot resolve {host}: {exc}")
    addrs = {i[4][0] for i in infos}
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if not allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                                  or ip.is_multicast or ip.is_unspecified):
            raise EgressDenied(f"{host} resolves to non-public address {a}")
    return {"host": host, "addresses": sorted(addrs)}
