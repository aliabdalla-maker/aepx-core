"""Pure MCP 2026-07-28 POST request contract gate; no HTTP or secrets."""
import json
from .mcp_contract_gate import MCPContractDenied
from .mcp_endpoint_policy import validate_mcp_endpoint

MAX_BODY = 262144

def validate_mcp_post_request(*, endpoint, approved_endpoints, method,
                              headers, body, expected_request_id,
                              negotiated_protocol_version=None,\n                              require_protocol_pin=False):
    validate_mcp_endpoint(endpoint=endpoint,approved_endpoints=approved_endpoints)
    if method != "POST" or not isinstance(headers,dict):
        raise MCPContractDenied("MCP requires a POST request")
    if any(not isinstance(k,str) or not isinstance(v,str) for k,v in headers.items()):
        raise MCPContractDenied("invalid MCP request headers")
    lowered={}
    for key,value in headers.items():
        name=key.lower()
        if name in lowered or not name.isascii() or not name.replace("-","").isalnum():
            raise MCPContractDenied("duplicate or malformed MCP header")
        if any(ord(c)<32 or ord(c)>126 for c in value):
            raise MCPContractDenied("unsafe MCP header value")
        lowered[name]=value
    if lowered.get("content-type") != "application/json":
        raise MCPContractDenied("MCP POST requires application/json")
    accept={part.strip().lower() for part in lowered.get("accept","").split(",")}
    if not {"application/json","text/event-stream"}.issubset(accept):
        raise MCPContractDenied("MCP POST must accept JSON and SSE")
    if require_protocol_pin and negotiated_protocol_version is None:\n        raise MCPContractDenied("trusted MCP protocol pin required")\n    if negotiated_protocol_version is not None:
        if (not isinstance(negotiated_protocol_version,str) or
            not negotiated_protocol_version or
            lowered.get("mcp-protocol-version") != negotiated_protocol_version):
            raise MCPContractDenied("MCP negotiated protocol version mismatch")
    if any(k in lowered for k in ("mcp-session-id","last-event-id")):
        raise MCPContractDenied("legacy MCP transport headers prohibited")
    if not isinstance(body,(bytes,str)):
        raise MCPContractDenied("invalid MCP request body")
    try:
        raw=body.encode("utf-8") if isinstance(body,str) else body
        if not raw or len(raw)>MAX_BODY:
            raise MCPContractDenied("oversized MCP request")
        def unique(pairs):
            out={}
            for k,v in pairs:
                if k in out:
                    raise MCPContractDenied("duplicate JSON key")
                out[k]=v
            return out
        message=json.loads(raw,object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise MCPContractDenied("invalid MCP request JSON") from exc
    if (not isinstance(message,dict) or message.get("jsonrpc")!="2.0" or
        not isinstance(message.get("method"),str) or
        not message["method"] or "result" in message or "error" in message or
        message.get("id")!=expected_request_id or
        type(message.get("id")) is not type(expected_request_id) or
        isinstance(message.get("id"),bool) or
        not isinstance(message.get("id"),(str,int))):
        raise MCPContractDenied("invalid or uncorrelated MCP JSON-RPC request")
    return {"endpoint":endpoint,"request_id":expected_request_id,
            "method":message["method"]}
