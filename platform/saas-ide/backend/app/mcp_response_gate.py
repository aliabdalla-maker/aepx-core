"""Pure MCP JSON-RPC response validation, no transport or side effects."""
import json
from .mcp_contract_gate import MCPContractDenied

_MAX_RESPONSE_BYTES = 262144

def validate_mcp_json_response(*, response_body, expected_request_id):
    """Fail closed on malformed, mismatched, oversized or ambiguous responses.

    JSON-RPC errors are returned as errors, never converted to successful tool
    results. Tool-level isError is also surfaced without hiding it.
    """
    if (not isinstance(response_body, (bytes, str)) or
        isinstance(expected_request_id, bool) or
        not isinstance(expected_request_id, (str, int))):
        raise MCPContractDenied("invalid MCP response inputs")
    raw = response_body.encode("utf-8") if isinstance(response_body, str) else response_body
    if not raw or len(raw) > _MAX_RESPONSE_BYTES:
        raise MCPContractDenied("MCP response exceeds size limit")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise MCPContractDenied("duplicate MCP JSON key")
            result[key] = value
        return result
    try:
        data = json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise MCPContractDenied("malformed MCP JSON response") from exc
    if (not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or
        type(data.get("id")) is not type(expected_request_id) or
        data.get("id") != expected_request_id or
        ("result" in data) == ("error" in data)):
        raise MCPContractDenied("invalid MCP JSON-RPC correlation or shape")
    if "error" in data:
        error = data["error"]
        if (not isinstance(error, dict) or
            type(error.get("code")) is not int or
            not isinstance(error.get("message"), str)):
            raise MCPContractDenied("malformed MCP JSON-RPC error")
        return {"ok": False, "error_code": error["code"]}
    result = data["result"]
    if not isinstance(result, dict):
        raise MCPContractDenied("invalid MCP tool result")
    if "isError" in result and type(result["isError"]) is not bool:
        raise MCPContractDenied("invalid MCP tool isError")
    if "content" not in result or not isinstance(result["content"], list):
        raise MCPContractDenied("invalid MCP tool content")
    return {"ok": not result.get("isError", False), "tool_error": result.get("isError", False),
            "content": result["content"]}
