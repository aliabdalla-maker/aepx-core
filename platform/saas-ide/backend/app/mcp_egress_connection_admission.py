"""Offline-only MCP egress connection admission contract.

This is NOT a transport or network enforcement implementation. A real gateway
must bind the validated IP at socket connect, enforce TLS SNI and certificate
hostname validation, block redirects, and disable proxy bypasses.
"""
from dataclasses import dataclass
from .mcp_http_preflight import MCPPreflight
from .mcp_egress_dns_policy import MCPDNSPin, MCPEgressDenied, verify_pinned_destination

@dataclass(frozen=True)
class MCPConnectionAdmission:
    hostname: str
    destination_ip: str
    port: int
    tls_server_name: str

def admit_mcp_connection(preflight, pin, *, connected_address, tls_server_name,
                         redirect_count=0, proxy_enabled=False):
    if type(preflight) is not MCPPreflight or type(pin) is not MCPDNSPin:
        raise MCPEgressDenied("validated preflight and DNS evidence required")
    if (type(redirect_count) is not int or redirect_count != 0
            or type(proxy_enabled) is not bool or proxy_enabled):
        raise MCPEgressDenied("redirect or proxy bypass prohibited")
    if (preflight.hostname != pin.hostname or preflight.port != 443
            or type(tls_server_name) is not str
            or tls_server_name != preflight.hostname
            or preflight.endpoint not in (f"https://{preflight.hostname}/mcp",
                                           f"https://{preflight.hostname}:443/mcp")
            and not preflight.endpoint.startswith(f"https://{preflight.hostname}/")
            and not preflight.endpoint.startswith(f"https://{preflight.hostname}:443/")):
        raise MCPEgressDenied("endpoint and TLS hostname mismatch")
    verify_pinned_destination(pin, hostname=preflight.hostname,
                              connected_address=connected_address)
    return MCPConnectionAdmission(preflight.hostname, connected_address, 443,
                                  tls_server_name)
