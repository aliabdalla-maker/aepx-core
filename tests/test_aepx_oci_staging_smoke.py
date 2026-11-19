import importlib.util
import pathlib
import unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-oci-staging-smoke.py"
spec=importlib.util.spec_from_file_location("aepx_oci_staging_smoke",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SmokeTests(unittest.TestCase):
    def test_unavailable_gateway_fails_closed(self):
        with patch.object(m.urllib.request,"urlopen",side_effect=m.urllib.error.URLError("offline")):
            self.assertFalse(m.probe("http://127.0.0.1:8000/health")["ok"])
    def test_healthy_gateway(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'{"status":"ok"}'
        with patch.object(m.urllib.request,"urlopen",return_value=Response()):
            self.assertTrue(m.probe("http://127.0.0.1:8000/health")["ok"])
if __name__=="__main__":unittest.main()
