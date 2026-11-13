"""Pure MCP HTTP response admission checks; no I/O or redirects.

The caller MUST enforce byte limits while streaming and reject redirects
before following them. This guard only validates supplied metadata.
"""
from dataclasses import dataclass

class MCPResponseDenied(PermissionError):
    pass

@dataclass(frozen=True)
class MCPResponsePolicy:
    max_response_bytes: int
    allowed_media_types: frozenset[str] = frozenset({
        "application/json", "text/event-stream"
    })

def validate_mcp_response(status, headers, *, policy):
    if type(policy) is not MCPResponsePolicy:
        raise MCPResponseDenied("typed response policy required")
    if type(policy.max_response_bytes) is not int or not 1 <= policy.max_response_bytes <= 4194304:
        raise MCPResponseDenied("invalid byte budget")
    if type(status) is not int or status != 200:
        raise MCPResponseDenied("non-success or redirect response rejected")
    if type(headers) is not dict:
        raise MCPResponseDenied("response headers required")
    normalized = {}
    for key, value in headers.items():
        if type(key) is not str or type(value) is not str:
            raise MCPResponseDenied("invalid header type")
        if not key.isascii() or not key or any(not (c.isalnum() or c == "-") for c in key):
            raise MCPResponseDenied("invalid header name")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise MCPResponseDenied("invalid header value")
        name = key.lower()
        if name in normalized:
            raise MCPResponseDenied("duplicate response header")
        normalized[name] = value
    content_type = normalized.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in policy.allowed_media_types:
        raise MCPResponseDenied("unsupported content type")
    length = normalized.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            raise MCPResponseDenied("invalid content length")
        if int(length) > policy.max_response_bytes:
            raise MCPResponseDenied("declared response exceeds budget")
    if "content-encoding" in normalized and normalized["content-encoding"].lower() != "identity":
        raise MCPResponseDenied("compressed responses require separate bounded decoder")
    return content_type

def enforce_mcp_response_chunk(total_bytes, chunk, *, policy):
    """Validate accumulated bytes; caller must enforce this per received chunk."""
    if type(policy) is not MCPResponsePolicy or type(policy.max_response_bytes) is not int or not 1 <= policy.max_response_bytes <= 4194304:
        raise MCPResponseDenied("invalid byte budget")
    if type(total_bytes) is not int or total_bytes < 0 or type(chunk) is not bytes:
        raise MCPResponseDenied("invalid response chunk")
    if len(chunk) > policy.max_response_bytes - total_bytes:
        raise MCPResponseDenied("response exceeds byte budget")
    return total_bytes + len(chunk)
