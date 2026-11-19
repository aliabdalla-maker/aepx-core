"""Offline bounded SSE parser for MCP JSON-RPC responses.

Accepts a complete bounded SSE byte buffer; no HTTP, sockets or streaming IO.
Every data event must correlate to the expected JSON-RPC request.
"""
from .mcp_contract_gate import MCPContractDenied
from .mcp_response_gate import validate_mcp_json_response

_MAX_STREAM_BYTES = 262144
_MAX_EVENTS = 32
_MAX_LINE_BYTES = 65536

def validate_mcp_sse_response(*, response_body, expected_request_id):
    if not isinstance(response_body, (bytes, str)):
        raise MCPContractDenied("invalid MCP SSE body")
    raw = response_body.encode("utf-8") if isinstance(response_body, str) else response_body
    if not raw or len(raw) > _MAX_STREAM_BYTES:
        raise MCPContractDenied("MCP SSE body exceeds size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise MCPContractDenied("invalid MCP SSE encoding") from exc
    if "\x00" in text or "\r" in text.replace("\r\n", ""):
        raise MCPContractDenied("unsafe MCP SSE control characters")
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n\n"):
        raise MCPContractDenied("incomplete MCP SSE event framing")
    events = 0
    lines_seen = 0
    response = None
    data_lines = []
    event_type = "message"
    for line in text.split("\n"):
        lines_seen += 1
        if lines_seen > 4096:
            raise MCPContractDenied("too many MCP SSE lines")
        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
            raise MCPContractDenied("oversized MCP SSE line")
        if not line:
            if data_lines:
                events += 1
                if events > _MAX_EVENTS or event_type != "message":
                    raise MCPContractDenied("unsupported MCP SSE event")
                if response is not None:
                    raise MCPContractDenied("multiple MCP SSE responses")
                response = validate_mcp_json_response(
                    response_body="\n".join(data_lines),
                    expected_request_id=expected_request_id)
            data_lines = []
            event_type = "message"
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].removeprefix(" "))
        elif line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("id:") or line.startswith("retry:"):
            raise MCPContractDenied("SSE resume and retry not supported")
        else:
            raise MCPContractDenied("unknown MCP SSE field")
    if response is None:
        raise MCPContractDenied("missing correlated MCP SSE response")
    return response
