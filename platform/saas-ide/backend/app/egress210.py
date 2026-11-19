"""Fail-closed provider/MCP egress policy preflight.

This is an application policy, NOT a substitute for a container firewall or
audited network proxy. Only an isolated network namespace can block SDK bypass.
"""
import ipaddress
import os
from urllib.parse import urlsplit
from .egress25 import validate_https_destination
from .egress27 import resolve_public

def approved_destination(url: str, *, allowed_hosts: set[str], resolver=None) -> tuple[str,str]:
    validate_https_destination(url,allowed_hosts=allowed_hosts)
    parsed=urlsplit(url)
    if parsed.port not in (None,443):
        raise PermissionError("Only port 443 permitted")
    if not parsed.hostname:
        raise PermissionError("Hostname required")
    ip=resolve_public(parsed.hostname,**({"resolver":resolver} if resolver else {}))
    if not ipaddress.ip_address(ip).is_global:
        raise PermissionError("Nonpublic destination")
    return parsed.hostname,ip

def assert_network_isolated():
    # Fail closed: application flags alone never establish a network boundary.
    # This can only be set by the reviewed sandbox entrypoint in a deployment
    # with independently verified firewall policy.
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true":
        raise PermissionError("External execution disabled")
    if os.getenv("IDE_NETWORK_ISOLATION_ATTESTED")!="true":
        raise PermissionError("OS-enforced egress isolation attestation missing")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED")!="true":
        raise PermissionError("Egress gateway verification missing")
