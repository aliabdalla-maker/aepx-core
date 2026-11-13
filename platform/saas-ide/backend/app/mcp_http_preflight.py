"""Offline-only MCP HTTPS preflight. This module never opens a socket.

A successful preflight is NOT permission to dispatch: the enforced egress
gateway must independently pin DNS, verify TLS and authorize each redirect.
"""
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

class MCPPreflightDenied(PermissionError):
    pass

@dataclass(frozen=True)
class MCPPreflight:
    endpoint: str
    hostname: str
    port: int
    timeout_seconds: int
    max_response_bytes: int

def validate_mcp_https_endpoint(endpoint, *, allowed_hosts, timeout_seconds=10,
                                max_response_bytes=1048576, authorization=None):
    if (type(endpoint) is not str or not endpoint or len(endpoint) > 2048
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in endpoint)):
        raise MCPPreflightDenied("invalid endpoint")
    if type(allowed_hosts) not in (frozenset, tuple, list) or not allowed_hosts:
        raise MCPPreflightDenied("explicit hostname allowlist required")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise MCPPreflightDenied("timeout outside safe bounds")
    if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 4194304:
        raise MCPPreflightDenied("response budget outside safe bounds")
    if type(authorization) is not str or not authorization.startswith("Bearer ") or len(authorization) <= 7:
        raise MCPPreflightDenied("bearer authorization required")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in authorization):
        raise MCPPreflightDenied("invalid authorization header")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port or 443
        host = parsed.hostname
    except ValueError as exc:
        raise MCPPreflightDenied("invalid endpoint syntax") from exc
    if (parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.query
            or not parsed.path.startswith("/") or port != 443
            or parsed.netloc.endswith(".") or "%" in parsed.netloc
            or "\\" in endpoint):
        raise MCPPreflightDenied("HTTPS endpoint violates strict transport policy")
    if host not in allowed_hosts:
        raise MCPPreflightDenied("hostname not allowlisted")
    if any(type(item) is not str or item != item.lower() for item in allowed_hosts):
        raise MCPPreflightDenied("invalid allowlist entry")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise MCPPreflightDenied("literal IP destinations prohibited")
    if host in ("localhost",) or "." not in host or any(
        not part or not part[0].isalnum() or not part[-1].isalnum()
        or not all(ch.isascii() and (ch.isalnum() or ch == "-") for ch in part)
        for part in host.split(".")
    ):
        raise MCPPreflightDenied("invalid public DNS hostname")
    return MCPPreflight(endpoint, host, port, timeout_seconds, max_response_bytes)
