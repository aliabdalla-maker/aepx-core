"""Pure DNS-answer classification for MCP egress gateway policy.

No DNS or sockets. Gateway MUST independently resolve and pin each actual
connection, disallow redirects and prohibit bypass of the gateway.
"""
import ipaddress
from urllib.parse import urlsplit
from .mcp_contract_gate import MCPContractDenied
from .mcp_endpoint_policy import validate_mcp_endpoint


def validate_mcp_dns_answers(*, endpoint, approved_endpoints, addresses):
    """Reject any untrusted/non-global address in a complete DNS answer set.

    A caller-supplied address set is NOT a trustworthy security boundary;
    production must obtain addresses in the enforced egress gateway.
    """
    validate_mcp_endpoint(endpoint=endpoint,approved_endpoints=approved_endpoints)
    if not isinstance(addresses,(tuple,list,set,frozenset)) or not 1 <= len(addresses) <= 16:
        raise MCPContractDenied("missing or oversized MCP DNS answer set")
    normalized=[]
    for value in addresses:
        if not isinstance(value,str) or not value or "%" in value:
            raise MCPContractDenied("invalid MCP DNS address")
        try:
            addr=ipaddress.ip_address(value)
        except ValueError as exc:
            raise MCPContractDenied("malformed MCP DNS address") from exc
        if not addr.is_global or getattr(addr,"ipv4_mapped",None) is not None:
            raise MCPContractDenied("non-global MCP DNS address")
        if str(addr) != value:
            raise MCPContractDenied("noncanonical MCP DNS address")
        normalized.append(addr)
    if len(set(normalized)) != len(normalized):
        raise MCPContractDenied("duplicate MCP DNS address")
    return {"hostname":urlsplit(endpoint).hostname,
            "addresses":tuple(sorted(str(addr) for addr in normalized))}


def validate_mcp_connected_peer(*, endpoint, approved_endpoints, addresses, peer_address):
    """Offline peer-address check for a transport-provided connection address.

    This does not inspect a real socket. The enforced gateway MUST obtain the
    peer from its own connected socket, not from request or response headers.
    """
    policy = validate_mcp_dns_answers(
        endpoint=endpoint, approved_endpoints=approved_endpoints, addresses=addresses
    )
    if not isinstance(peer_address, str) or peer_address not in policy["addresses"]:
        raise MCPContractDenied("MCP peer is not in the approved pinned DNS set")
    return policy
