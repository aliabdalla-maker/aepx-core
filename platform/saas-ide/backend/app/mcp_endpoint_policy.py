"""Offline MCP endpoint and redirect policy. No DNS lookup or network access.

Caller MUST separately enforce pinned DNS/IP, TLS verification, egress proxy
and OAuth token audience at actual connection time. URL checks alone are not SSRF
protection.
"""
import ipaddress
from urllib.parse import urlsplit
from .mcp_contract_gate import MCPContractDenied


def validate_mcp_endpoint(*, endpoint, approved_endpoints):
    """Require an exact, canonical HTTPS endpoint from trusted policy."""
    if (not isinstance(endpoint, str) or not isinstance(approved_endpoints,
            (set, frozenset, tuple, list)) or endpoint not in approved_endpoints
            or len(endpoint) > 2048 or not endpoint.isascii()):
        raise MCPContractDenied("MCP endpoint not exactly allowlisted")
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in endpoint):
        raise MCPContractDenied("unsafe MCP endpoint characters")
    try:
        url = urlsplit(endpoint)
        host = url.hostname
        port = url.port
    except ValueError as exc:
        raise MCPContractDenied("malformed MCP endpoint") from exc
    if (url.scheme != "https" or not host or not url.netloc or
        url.username is not None or url.password is not None or
        url.fragment or url.query or url.path.startswith("//") or
        port not in (None, 443)):
        raise MCPContractDenied("unsafe MCP endpoint shape")
    if (url.netloc != host and url.netloc != host + ":443"):
        raise MCPContractDenied("noncanonical MCP host or port")
    if (host != host.lower() or host.endswith(".") or
        not all(part and len(part) <= 63 for part in host.split(".")) or
        len(host) > 253 or "." not in host or
        any(not all(c.isascii() and (c.isalnum() or c == "-") for c in part)
            or part.startswith("-") or part.endswith("-")
            for part in host.split("."))):
        raise MCPContractDenied("invalid MCP DNS host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise MCPContractDenied("IP-literal MCP endpoint prohibited")
    if ("%" in endpoint or "\\" in endpoint or
        endpoint != url.geturl()):
        raise MCPContractDenied("noncanonical MCP endpoint")
    return endpoint
