"""Fail-closed URL validation. Actual enforcement MUST be at the network layer."""
import ipaddress
from urllib.parse import urlsplit

def validate_https_destination(url: str, *, allowed_hosts: set[str]) -> str:
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise PermissionError("HTTPS destination required")
    if parsed.hostname.endswith("."):
        raise PermissionError("Noncanonical hostname forbidden")
    host=parsed.hostname.lower()
    if host not in allowed_hosts or not host or any(c.isspace() for c in host):
        raise PermissionError("Destination not allowlisted")
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        if host=="localhost" or host.endswith((".local",".internal",".localhost")):
            raise PermissionError("Internal hostname forbidden")
    else:
        if not address.is_global:
            raise PermissionError("Non-global address forbidden")
    return url

def assert_egress_configured() -> None:
    # Config is deliberately insufficient to enable network traffic. Production
    # must enforce DNS/IP policies with a dedicated outbound gateway and firewall.
    import os
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true":
        raise PermissionError("External execution disabled")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED")!="true":
        raise PermissionError("Egress gateway unverified")
