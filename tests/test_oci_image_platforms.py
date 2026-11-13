import importlib.util
from pathlib import Path
import json
import unittest
from unittest.mock import Mock
path=Path(__file__).resolve().parents[1]/"deploy/oci/verify-image-platforms.py"
spec=importlib.util.spec_from_file_location("image_platforms",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def result(arches,returncode=0):
    return Mock(returncode=returncode,stdout=json.dumps({"manifests":[
        {"platform":{"os":"linux","architecture":arch}} for arch in arches]}))
class PlatformTests(unittest.TestCase):
    def test_arm64_supported(self):
        self.assertEqual(m.verify(run=lambda *a,**kw:result(["amd64","arm64"]),machine="aarch64"),"arm64")
    def test_amd64_supported(self):
        self.assertEqual(m.verify(run=lambda *a,**kw:result(["amd64"]),machine="x86_64"),"amd64")
    def test_arm64_missing_fails(self):
        with self.assertRaises(RuntimeError):
            m.verify(run=lambda *a,**kw:result(["amd64"]),machine="aarch64")
    def test_manifest_error_fails(self):
        with self.assertRaises(RuntimeError):
            m.verify(run=lambda *a,**kw:result([],1),machine="x86_64")
    def test_unknown_host_fails(self):
        with self.assertRaises(RuntimeError):
            m.verify(run=lambda *a,**kw:result(["amd64"]),machine="unknown")
    def test_single_image_manifest_not_proof(self):
        self.assertFalse(m.supports({"schemaVersion":2},"amd64"))
if __name__=="__main__":unittest.main()
