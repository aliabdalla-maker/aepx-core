"""Offline MCP initialize response gate; never authenticates a remote server.

Caller must supply bytes from an independently authenticated TLS/OAuth channel.
"""
import json
from .mcp_contract_gate import MCPContractDenied
from .mcp_version_policy import select_mcp_protocol_version

MAX_INITIALIZE_BYTES=65536

def validate_mcp_initialize_response(*, response_body, expected_request_id,
                                     client_versions, expected_server_name=None):
    if not isinstance(response_body,(bytes,str)):
        raise MCPContractDenied("invalid MCP initialize response")
    try:
        raw=response_body.encode("utf-8") if isinstance(response_body,str) else response_body
        if not raw or len(raw)>MAX_INITIALIZE_BYTES:
            raise MCPContractDenied("MCP initialize response size invalid")
        def unique(pairs):
            out={}
            for key,value in pairs:
                if key in out:
                    raise MCPContractDenied("duplicate initialize JSON key")
                out[key]=value
            return out
        msg=json.loads(raw,object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise MCPContractDenied("invalid MCP initialize JSON") from exc
    if (not isinstance(msg,dict) or msg.get("jsonrpc")!="2.0" or
        msg.get("id")!=expected_request_id or
        isinstance(msg.get("id"),bool) or
        not isinstance(msg.get("id"),(str,int)) or
        "error" in msg or "method" in msg or
        not isinstance(msg.get("result"),dict)):
        raise MCPContractDenied("uncorrelated MCP initialize response")
    result=msg["result"]
    if (not isinstance(result.get("capabilities"),dict) or
        not isinstance(result.get("serverInfo"),dict) or
        not isinstance(result["serverInfo"].get("name"),str) or
        not result["serverInfo"]["name"] or
        len(result["serverInfo"]["name"])>256):
        raise MCPContractDenied("incomplete MCP server initialization")
    if expected_server_name is not None and (
        not isinstance(expected_server_name,str) or
        not expected_server_name or
        result["serverInfo"]["name"] != expected_server_name
    ):
        raise MCPContractDenied("MCP initialized server name mismatch")
    selected=select_mcp_protocol_version(
        server_version=result.get("protocolVersion"),
        client_versions=client_versions)
    return {"version":selected["version"],
            "transport_profile":selected["transport_profile"],
            "server_name":result["serverInfo"]["name"],
            "capabilities":result["capabilities"]}
