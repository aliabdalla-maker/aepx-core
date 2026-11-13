"""Offline MCP initialized notification gate, no transport or side effects."""
import json
from .mcp_contract_gate import MCPContractDenied

def validate_mcp_initialized_notification(*, body, initialized_version,
                                          expected_version):
    if (not isinstance(initialized_version,str) or
        initialized_version!=expected_version or
        not initialized_version):
        raise MCPContractDenied("MCP initialization version not pinned")
    if not isinstance(body,(bytes,str)):
        raise MCPContractDenied("invalid initialized notification")
    try:
        raw=body.encode("utf-8") if isinstance(body,str) else body
        if not raw or len(raw)>4096:
            raise MCPContractDenied("initialized notification size invalid")
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:
                    raise MCPContractDenied("duplicate initialized JSON key")
                result[key]=value
            return result
        msg=json.loads(raw,object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise MCPContractDenied("invalid initialized notification JSON") from exc
    if (not isinstance(msg,dict) or msg.get("jsonrpc")!="2.0" or
        msg.get("method")!="notifications/initialized" or
        "id" in msg or "result" in msg or "error" in msg or
        any(key not in ("jsonrpc","method","params") for key in msg) or
        ("params" in msg and msg["params"]!={})):
        raise MCPContractDenied("invalid MCP initialized notification shape")
    return {"version":initialized_version,"method":"notifications/initialized"}
