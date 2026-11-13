"""Offline usage ledger tests. No provider calls."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ledger",ROOT/"scripts/aepx_autonomous_usage_ledger.py")
ledger=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)

def fresh():
    return {"version":1,"cap_usd":"10","spent_usd":"0","receipts":{}}

def charge(value,request_id="req-1",input_tokens=1000,output_tokens=500):
    return ledger.record_receipt(value,request_id=request_id,input_tokens=input_tokens,
        output_tokens=output_tokens,input_usd_per_million="1",
        output_usd_per_million="2")

class LedgerTests(unittest.TestCase):
    def test_valid_receipt(self):
        result=charge(fresh())
        self.assertEqual(result["spent_usd"],"0.002")
        self.assertEqual(len(result["receipts"]),1)

    def test_duplicate_rejected(self):
        with self.assertRaises(ledger.AccountingDenied):
            charge(charge(fresh()))

    def test_total_tampering_rejected(self):
        state=charge(fresh())
        state["spent_usd"]="0"
        with self.assertRaises(ledger.AccountingDenied):
            ledger.validate_ledger(state)

    def test_invalid_token_counts(self):
        for value in (-1,True,1.5,"12"):
            with self.subTest(value=value),self.assertRaises(ledger.AccountingDenied):
                charge(fresh(),input_tokens=value)

    def test_invalid_money(self):
        for value in ("NaN","Infinity","-1",True,1.1):
            with self.subTest(value=value),self.assertRaises(ledger.AccountingDenied):
                ledger.money(value)

    def test_cap_and_reservation(self):
        state=fresh()
        self.assertTrue(ledger.can_start_request(state,reserved_usd="9"))
        for reserve in ("10","11","0"):
            with self.subTest(reserve=reserve),self.assertRaises(ledger.AccountingDenied):
                ledger.can_start_request(state,reserved_usd=reserve)
        state["cap_usd"]="0.002"
        with self.assertRaises(ledger.AccountingDenied):
            charge(state)

    def test_reject_missing_receipt_fields(self):
        state=fresh()
        state["receipts"]={"req":{"input_tokens":1}}
        with self.assertRaises(ledger.AccountingDenied):
            ledger.validate_ledger(state)

if __name__=="__main__":
    unittest.main()
