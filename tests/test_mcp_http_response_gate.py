"""Offline HTTP media/status dispatch adversarial tests."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform/saas-ide/backend"))
from app.mcp_http_response_gate import validate_mcp_http_response
from app.mcp_contract_gate import MCPContractDenied

BODY=json.dumps({"jsonrpc":"2.0","id":7,"result":{"content":[]}})

class TestMCPHTTPResponseGate(unittest.TestCase):
    def call(self,status,media,body):
        return validate_mcp_http_response(
            status_code=status,content_type=media,
            response_body=body,expected_request_id=7)
    def test_json_and_sse(self):
        self.assertTrue(self.call(200,"application/json; charset=utf-8",BODY)["ok"])
        self.assertTrue(self.call(200,"text/event-stream; charset=utf-8",
                                  "data: "+BODY+"\\n\\n".replace("\\n","\n"))["ok"])
    def test_fail_closed(self):
        for status,media,body in [
            (202,"application/json",BODY),
            (204,"application/json",BODY),
            (302,"application/json",BODY),
            (401,"application/json",BODY),
            (500,"application/json",BODY),
            (True,"application/json",BODY),
            (200,"text/html",BODY),
            (200,"application/json",b""),
            (200,"application/json",BODY.encode()*100000),
            (200,"application/json",BODY.replace('"id": 7','"id": 8')),
            (200,"text/event-stream","data: "+BODY),
        ]:
            with self.subTest(status=status,media=media),self.assertRaises(MCPContractDenied):
                self.call(status,media,body)
