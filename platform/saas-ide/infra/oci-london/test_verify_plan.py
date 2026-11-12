import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("verify_plan", Path(__file__).with_name("verify-plan.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class PlanTests(unittest.TestCase):
    def test_blocks_missing_resources(self):
        self.assertTrue(mod.inspect({}))
    def test_blocks_paid_shape_and_public_ip(self):
        plan = {"resource_changes": [{"address": "oci_core_instance.staging[0]", "type": "oci_core_instance",
                "change": {"actions": ["create"], "after": {"shape": "VM.Standard.E4.Flex",
                "create_vnic_details": [{"assign_public_ip": True}]}}}]}
        errors = mod.inspect(plan)
        self.assertIn("Non-A1 Compute shape", errors)
        self.assertIn("Public IP must be disabled", errors)
    def test_blocks_destructive_change(self):
        plan = {"resource_changes": [{"address": "oci_core_vcn.aepx", "type": "oci_core_vcn",
                "change": {"actions": ["delete"], "after": {}}}]}
        self.assertTrue(any("mutation" in x for x in mod.inspect(plan)))
    def test_rejects_unverified_a1_sizing(self):
        plan = {"resource_changes": [{"address": "oci_core_instance.staging[0]", "type": "oci_core_instance",
                "change": {"actions": ["create"], "after": {"shape": "VM.Standard.A1.Flex",
                "create_vnic_details": [{"assign_public_ip": False}]}}}]}
        self.assertIn("Explicit A1 sizing required", mod.inspect(plan))

    def test_rejects_public_subnet(self):
        plan = {"resource_changes": [{"address": "oci_core_subnet.private", "type": "oci_core_subnet",
                "change": {"actions": ["create"], "after": {"prohibit_public_ip_on_vnic": False}}}]}
        self.assertIn("Subnet must prohibit public IP addresses", mod.inspect(plan))

    def test_rejects_existing_resource_noop(self):
        plan = {"resource_changes": [{"address": "oci_core_vcn.aepx", "type": "oci_core_vcn",
                "change": {"actions": ["no-op"], "after": {}}}]}
        self.assertTrue(any("Only new resource creation" in x for x in mod.inspect(plan)))

    def test_accepts_private_a1_create(self):
        plan = {"resource_changes": [{"address": "oci_core_instance.staging[0]", "type": "oci_core_instance",
                "change": {"actions": ["create"], "after": {"shape": "VM.Standard.A1.Flex",
                "create_vnic_details": [{"assign_public_ip": False}],
                "shape_config": [{"ocpus": 1, "memory_in_gbs": 6}],
                "source_details": [{"boot_volume_size_in_gbs": 50}]}}}]}
        self.assertEqual(mod.inspect(plan), [])

if __name__ == "__main__":
    unittest.main()
