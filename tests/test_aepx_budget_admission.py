"""Fail-closed offline budget admission regression tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aepx_budget_admission import admit, BudgetDenied

LIMITS = {"tokens":1000,"cost_usd":"2.00","seconds":120,"repair_attempts":3}
USED = {"tokens":200,"cost_usd":"0.50","seconds":20,"repair_attempts":1}
PLAN = {"tokens":300,"cost_usd":"0.75","seconds":30,"repair_attempts":1}

class BudgetAdmissionTests(unittest.TestCase):
    def test_accepts_without_execution_authority(self):
        result = admit(LIMITS,USED,PLAN)
        self.assertTrue(result["admitted"])
        self.assertFalse(result["reserved"])
        self.assertFalse(result["external_execution_authorized"])

    def test_denies_exhausted_tokens(self):
        with self.assertRaisesRegex(BudgetDenied,"tokens"):
            admit(LIMITS,USED,{**PLAN,"tokens":801})

    def test_denies_exhausted_cost(self):
        with self.assertRaisesRegex(BudgetDenied,"cost_usd"):
            admit(LIMITS,USED,{**PLAN,"cost_usd":"1.500001"})

    def test_denies_float_money(self):
        with self.assertRaises(BudgetDenied):
            admit(LIMITS,USED,{**PLAN,"cost_usd":0.2})

    def test_denies_nonfinite_money(self):
        with self.assertRaises(BudgetDenied):
            admit(LIMITS,USED,{**PLAN,"cost_usd":"NaN"})

    def test_denies_extra_fields(self):
        with self.assertRaises(BudgetDenied):
            admit({**LIMITS,"override":True},USED,PLAN)

    def test_denies_boolean_integer(self):
        with self.assertRaises(BudgetDenied):
            admit(LIMITS,USED,{**PLAN,"tokens":True})

    def test_denies_repair_overflow(self):
        with self.assertRaisesRegex(BudgetDenied,"repair_attempts"):
            admit(LIMITS,USED,{**PLAN,"repair_attempts":3})

if __name__ == "__main__":
    unittest.main()
