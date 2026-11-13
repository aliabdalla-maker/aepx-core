"""Offline composition of MCP endpoint, DNS and HTTP response gates.

No network access, no DNS resolution and no authority to dispatch tools.
The enforced gateway must independently obtain DNS answers and verify
connection destination, TLS identity, token audience and redirect policy.
"""
from .mcp_contract_gate import MCPContractDenied
from .mcp_endpoint_policy import validate_mcp_endpoint
from .mcp_dns_policy import validate_mcp_dns_answers
from .mcp_http_response_gate import validate_mcp_http_response


def prepare_mcp_transport_policy(*, endpoint, approved_endpoints, dns_answers,
                                 approved_server_id, requested_server_id):
    if (not isinstance(approved_server_id,str) or not approved_server_id or
        requested_server_id != approved_server_id):
        raise MCPContractDenied("MCP server identity mismatch")
    validate_mcp_endpoint(endpoint=endpoint,approved_endpoints=approved_endpoints)
    dns=validate_mcp_dns_answers(endpoint=endpoint,
                                  approved_endpoints=approved_endpoints,
                                  addresses=dns_answers)
    return {"endpoint":endpoint,"server_id":approved_server_id,
            "hostname":dns["hostname"],"addresses":dns["addresses"]}


def validate_mcp_transport_result(*, policy, endpoint, server_id, status_code,
                                  content_type, response_body, expected_request_id):
    """Check immutable preflight identity before offline response validation."""
    if (not isinstance(policy,dict) or policy.get("endpoint") != endpoint or
        policy.get("server_id") != server_id or
        not isinstance(policy.get("addresses"),tuple) or
        not policy["addresses"]):
        raise MCPContractDenied("MCP transport policy mismatch")
    return validate_mcp_http_response(
        status_code=status_code,content_type=content_type,
        response_body=response_body,expected_request_id=expected_request_id)
