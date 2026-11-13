import copy
import importlib.util
from pathlib import Path
import unittest
import yaml
path=Path(__file__).resolve().parents[1]/"deploy/oci/check-staging-policy.py"
spec=importlib.util.spec_from_file_location("staging_policy",path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=yaml.safe_load(m.COMPOSE.read_text())
    def test_real_staging_config(self):
        self.assertEqual(m.check(self.cfg),[])
    def test_public_port_rejected(self):
        self.cfg["services"]["redis"]["ports"]=["6379:6379"]
        self.assertTrue(m.check(self.cfg))
    def test_privileged_rejected(self):
        self.cfg["services"]["identity"]["privileged"]=True
        self.assertTrue(m.check(self.cfg))
    def test_missing_memory_rejected(self):
        self.cfg["services"]["trust"].pop("mem_limit")
        self.assertTrue(m.check(self.cfg))
    def test_excess_memory_rejected(self):
        self.cfg["services"]["postgres"]["mem_limit"]="3000m"
        self.assertTrue(m.check(self.cfg))
    def test_unapproved_service_rejected(self):
        self.cfg["services"]["unknown"]={}
        self.assertTrue(m.check(self.cfg))
    def test_unmounted_named_volume_rejected(self):
        self.cfg["services"]["postgres"]["volumes"]=["other-volume:/var/lib/postgresql/data"]
        self.assertTrue(m.check(self.cfg))
    def test_missing_volume_rejected(self):
        self.cfg["volumes"].pop("staging-postgres")
        self.assertTrue(m.check(self.cfg))
if __name__=="__main__":unittest.main()
