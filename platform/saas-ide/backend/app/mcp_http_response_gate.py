"""Pure MCP HTTP response gate. No network, credentials or side effects."""
from .mcp_contract_gate import MCPContractDenied
from .mcp_response_gate import validate_mcp_json_response
from .mcp_sse_gate import validate_mcp_sse_response

_MAX_RESPONSE_BYTES = 262144


def validate_mcp_http_response(*, status_code, content_type,
                               response_body, expected_request_id):
    """Route a bounded successful JSON-RPC request response by media type.

    This is intentionally only a *response* validator; HTTP TLS, redirects,
    authentication, endpoint allowlists and streaming deadlines are external.
    """
    if type(status_code) is not int or status_code != 200:
        raise MCPContractDenied("unexpected MCP HTTP response status")
    if not isinstance(content_type, str) or not content_type:
        raise MCPContractDenied("missing MCP HTTP media type")
    if not isinstance(response_body, (str, bytes)):
        raise MCPContractDenied("invalid MCP HTTP response body")
    try:
        raw = response_body.encode("utf-8") if isinstance(response_body, str) else response_body
    except UnicodeError as exc:
        raise MCPContractDenied("invalid MCP HTTP encoding") from exc
    if not raw or len(raw) > _MAX_RESPONSE_BYTES:
        raise MCPContractDenied("MCP HTTP response exceeds size limit")
    media = content_type.split(";", 1)[0].strip().lower()
    if media == "application/json":
        return validate_mcp_json_response(
            response_body=raw, expected_request_id=expected_request_id)
    if media == "text/event-stream":
        return validate_mcp_sse_response(
            response_body=raw, expected_request_id=expected_request_id)
    raise MCPContractDenied("unsupported MCP HTTP response media type")
