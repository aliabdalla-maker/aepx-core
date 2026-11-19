"""Offline MCP transport policy composition regressions."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_transport_policy import prepare_mcp_transport_policy,validate_mcp_transport_result
from app.mcp_contract_gate import MCPContractDenied

URL="https://mcp.example.test/mcp"
BODY=json.dumps({"jsonrpc":"2.0","id":7,"result":{"content":[]}})

class TestTransportPolicy(unittest.TestCase):
    def policy(self,**changes):
        values=dict(endpoint=URL,approved_endpoints={URL},
                    dns_answers=["1.1.1.1"],approved_server_id="crm",
                    requested_server_id="crm")
        values.update(changes)
        return prepare_mcp_transport_policy(**values)
    def test_validated_offline_chain(self):
        policy=self.policy()
        self.assertEqual(policy["addresses"],("1.1.1.1",))
        result=validate_mcp_transport_result(
            policy=policy,endpoint=URL,server_id="crm",status_code=200,
            content_type="application/json",response_body=BODY,expected_request_id=7)
        self.assertTrue(result["ok"])
    def test_preflight_denies_wrong_server_and_dns(self):
        for changes in ({"requested_server_id":"rogue"},
                        {"dns_answers":["127.0.0.1"]},
                        {"approved_endpoints":{"https://other.example.test/mcp"}}):
            with self.subTest(changes=changes),self.assertRaises(MCPContractDenied):
                self.policy(**changes)
    def test_response_denies_endpoint_server_and_request_mismatch(self):
        policy=self.policy()
        for endpoint,server,request_id in (
            ("https://other.example.test/mcp","crm",7),
            (URL,"rogue",7),
            (URL,"crm",8)):
            with self.subTest(endpoint=endpoint,server=server,request_id=request_id):
                with self.assertRaises(MCPContractDenied):
                    validate_mcp_transport_result(
                        policy=policy,endpoint=endpoint,server_id=server,
                        status_code=200,content_type="application/json",
                        response_body=BODY,expected_request_id=request_id)

    def test_connected_peer_must_match_pinned_answers(self):
        policy=self.policy()
        ok=validate_mcp_transport_result(
            policy=policy,endpoint=URL,server_id="crm",status_code=200,
            content_type="application/json",response_body=BODY,
            expected_request_id=7,connected_peer="1.1.1.1")
        self.assertTrue(ok["ok"])
        for peer in ("8.8.8.8","127.0.0.1","169.254.169.254"):
            with self.subTest(peer=peer),self.assertRaises(MCPContractDenied):
                validate_mcp_transport_result(
                    policy=policy,endpoint=URL,server_id="crm",status_code=200,
                    content_type="application/json",response_body=BODY,
                    expected_request_id=7,connected_peer=peer)

    def test_strict_transport_requires_peer_evidence(self):
        policy=self.policy()
        common=dict(policy=policy,endpoint=URL,server_id="crm",status_code=200,
                    content_type="application/json",response_body=BODY,
                    expected_request_id=7,require_connected_peer=True)
        with self.assertRaises(MCPContractDenied):
            validate_mcp_transport_result(**common)
        self.assertTrue(validate_mcp_transport_result(
            **common,connected_peer="1.1.1.1")["ok"])

    def test_mutated_transport_policy_fails_closed(self):
        common=dict(endpoint=URL,server_id="crm",status_code=200,
                    content_type="application/json",response_body=BODY,
                    expected_request_id=7,connected_peer="1.1.1.1",
                    require_connected_peer=True)
        for mutation in (
            {"addresses":("127.0.0.1",)},
            {"addresses":("1.1.1.1","10.0.0.1")},
            {"addresses":("1.1.1.1","1.1.1.1")},
            {"addresses":("8.8.8.8","1.1.1.1")},
            {"hostname":"other.example.test"},
        ):
            policy=self.policy()
            policy.update(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(MCPContractDenied):
                validate_mcp_transport_result(policy=policy,**common)
