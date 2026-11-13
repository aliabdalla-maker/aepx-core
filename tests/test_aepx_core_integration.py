#!/usr/bin/env python3
"""Offline regression tests for read-only acceptance probes."""
import importlib.util
import io
import json
import pathlib
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).resolve().parents[1] / "scripts/aepx-core-integration.py"
spec = importlib.util.spec_from_file_location("aepx_core_integration", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.body[:size]

class CoreProbeTests(unittest.TestCase):
    def test_valid_openapi(self):
        payload=json.dumps({"openapi":"3.1.0","info":{"title":"AEP-X"},"paths":{"/health":{}}}).encode()
        with patch.object(module.urllib.request,"urlopen",return_value=FakeResponse(payload)):
            result=module.probe("gateway","http://127.0.0.1:8000",1,0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["path_count"],1)
    def test_empty_paths_allowed_for_running_api(self):
        payload=json.dumps({"openapi":"3.1.0","info":{"title":"AEP-X"},"paths":{}}).encode()
        with patch.object(module.urllib.request,"urlopen",return_value=FakeResponse(payload)):
            self.assertTrue(module.probe("gateway","http://localhost",1,0)["passed"])
    def test_invalid_json_fails(self):
        with patch.object(module.urllib.request,"urlopen",return_value=FakeResponse(b"not json")):
            self.assertFalse(module.probe("gateway","http://localhost",1,0)["passed"])
    def test_non_200_fails(self):
        with patch.object(module.urllib.request,"urlopen",return_value=FakeResponse(b"{}",503)):
            self.assertFalse(module.probe("gateway","http://localhost",1,0)["passed"])
    def test_retry_clears_transient_error(self):
        payload=json.dumps({"openapi":"3.1.0","info":{},"paths":{}}).encode()
        with patch.object(module.urllib.request,"urlopen",side_effect=[ConnectionError("startup"),FakeResponse(payload)]):
            with patch.object(module.time,"sleep"):
                result=module.probe("gateway","http://localhost",2,0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["attempts"],2)
        self.assertNotIn("error",result)

if __name__=="__main__":
    unittest.main()
