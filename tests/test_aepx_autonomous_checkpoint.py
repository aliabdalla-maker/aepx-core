"""Offline checkpoint controller regression tests."""
import copy
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aepx_checkpoint", ROOT / "scripts/aepx_autonomous_checkpoint.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def state():
    return {"schema_version":1,"iteration":1,"max_iterations":10000,
            "release_ready":False,
            "safety":{"auto_merge":False,"auto_deploy":False,
                      "external_mcp_execution":False,"chargeable_oci":False}}

class CheckpointTests(unittest.TestCase):
    def test_successful_offline_checkpoint(self):
        result = module.next_checkpoint(state(), outcome="passed",
                  evidence="targeted tests verified", max_spend_usd=25, spent_usd=1)
        self.assertEqual(result["iteration"], 2)
        self.assertEqual(result["status"], "checkpoint-passed")

    def test_privileged_controls_fail_closed(self):
        for key in module.FORBIDDEN:
            value = state()
            value["safety"][key] = True
            with self.subTest(key=key), self.assertRaises(module.RunnerDenied):
                module.validate_progress(value)

    def test_iteration_and_release_limits(self):
        for change in ({"iteration":10001},{"max_iterations":10001},
                       {"iteration":True},{"release_ready":True}):
            value = state()
            value.update(change)
            with self.subTest(change=change), self.assertRaises(module.RunnerDenied):
                module.validate_progress(value)

    def test_budget_exhaustion_and_nonfinite_values(self):
        for spent, cap in ((25,25),(26,25),(-1,25),(math.nan,25),
                           (1,math.inf),(1,math.nan)):
            with self.subTest(spent=spent, cap=cap), self.assertRaises(module.RunnerDenied):
                module.next_checkpoint(state(), outcome="passed",
                  evidence="evidence", max_spend_usd=cap, spent_usd=spent)

    def test_requires_evidence(self):
        with self.assertRaises(module.RunnerDenied):
            module.next_checkpoint(state(), outcome="passed",
                 evidence="", max_spend_usd=25, spent_usd=1)

    def test_atomic_save_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(module.RunnerDenied):
                module.atomic_save(Path(folder) / "missing.json", state())

if __name__ == "__main__":
    unittest.main()
