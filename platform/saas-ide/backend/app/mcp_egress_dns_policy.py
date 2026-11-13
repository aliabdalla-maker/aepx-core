"""Offline-only DNS answer validation for a future enforced MCP egress gateway.

No DNS lookup or network I/O. Caller MUST enforce pinned destination IP at
socket connect, TLS hostname verification, and fresh policy on each request.
"""
from dataclasses import dataclass
from ipaddress import ip_address

class MCPEgressDenied(PermissionError):
    pass

@dataclass(frozen=True)
class MCPDNSPin:
    hostname: str
    addresses: tuple[str, ...]

def validate_dns_answers(hostname, answers, *, allowed_hosts):
    if (type(hostname) is not str or not hostname or hostname != hostname.lower()
            or len(hostname) > 253 or hostname.endswith(".") or "." not in hostname):
        raise MCPEgressDenied("noncanonical hostname")
    if any(not part or len(part) > 63 or not part[0].isalnum()
           or not part[-1].isalnum() or not all(
               ch.isascii() and (ch.isalnum() or ch == "-") for ch in part)
           for part in hostname.split(".")):
        raise MCPEgressDenied("invalid hostname")
    if (type(allowed_hosts) is not frozenset or not allowed_hosts
            or any(type(host) is not str for host in allowed_hosts)
            or hostname not in allowed_hosts):
        raise MCPEgressDenied("hostname not allowlisted")
    if type(answers) not in (tuple, list) or not 1 <= len(answers) <= 16:
        raise MCPEgressDenied("missing or excessive DNS answers")
    addresses = []
    for answer in answers:
        if type(answer) is not str or not answer or answer != answer.strip():
            raise MCPEgressDenied("invalid DNS address")
        try:
            parsed = ip_address(answer)
        except ValueError as exc:
            raise MCPEgressDenied("invalid DNS address") from exc
        if not parsed.is_global or getattr(parsed, "ipv4_mapped", None) is not None:
            raise MCPEgressDenied("nonpublic DNS destination")
        if str(parsed) != answer:
            raise MCPEgressDenied("noncanonical DNS address")
        if answer in addresses:
            raise MCPEgressDenied("duplicate DNS answer")
        addresses.append(answer)
    return MCPDNSPin(hostname, tuple(addresses))

def verify_pinned_destination(pin, *, hostname, connected_address):
    """Check a proposed socket destination against validated DNS evidence.

    This is NOT socket-level enforcement; the network gateway must enforce it.
    """
    if (type(pin) is not MCPDNSPin or type(hostname) is not str
            or hostname != pin.hostname or type(connected_address) is not str
            or connected_address not in pin.addresses):
        raise MCPEgressDenied("destination does not match pinned DNS answers")
    return True
