"""Offline reservation ledger regression tests."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from aepx_budget_ledger import reserve, settle
from aepx_budget_admission import BudgetDenied

LIMITS={"tokens":100,"cost_usd":"1.00","seconds":60,"repair_attempts":3}
PLAN={"tokens":60,"cost_usd":"0.60","seconds":40,"repair_attempts":2}
ACTUAL={"tokens":30,"cost_usd":"0.30","seconds":20,"repair_attempts":1}

class LedgerTests(unittest.TestCase):
    def test_reserve_idempotent_and_settle(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            self.assertEqual(reserve(path,"req-1",LIMITS,PLAN)["status"],"reserved")
            self.assertEqual(reserve(path,"req-1",LIMITS,PLAN)["status"],"already_reserved")
            self.assertEqual(settle(path,"req-1",ACTUAL)["status"],"settled")
            self.assertEqual(settle(path,"req-1",ACTUAL)["status"],"already_settled")
            self.assertEqual(reserve(path,"req-2",LIMITS,PLAN)["status"],"reserved")

    def test_denies_concurrent_overspend(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            reserve(path,"req-1",LIMITS,PLAN)
            with self.assertRaisesRegex(BudgetDenied,"tokens"):
                reserve(path,"req-2",LIMITS,PLAN)

    def test_conflicting_replay_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            reserve(path,"req-1",LIMITS,PLAN)
            with self.assertRaisesRegex(BudgetDenied,"conflicting"):
                reserve(path,"req-1",LIMITS,{**PLAN,"tokens":50})

    def test_settlement_over_reservation_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            reserve(path,"req-1",LIMITS,PLAN)
            with self.assertRaisesRegex(BudgetDenied,"tokens"):
                settle(path,"req-1",{**ACTUAL,"tokens":61})

    def test_unknown_settlement_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(BudgetDenied,"unknown"):
                settle(Path(folder)/"budget.json","missing",ACTUAL)

    def test_rejects_invalid_persisted_request_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            path.write_text(json.dumps({"schema_version":1,"reservations":{
                "../escape":{"reserved":PLAN,"settled":None}}}),encoding="utf-8")
            with self.assertRaisesRegex(BudgetDenied,"persisted request id"):
                reserve(path,"safe",LIMITS,PLAN)

    def test_rejects_oversized_ledger_before_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(BudgetDenied,"size limit"):
                reserve(path,"safe",LIMITS,PLAN)

    def test_rejects_reservation_count_overflow(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            data={"schema_version":1,"reservations":{
                f"req-{i}":{"reserved":PLAN,"settled":None} for i in range(10000)}}
            path.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(BudgetDenied,"count limit"):
                reserve(path,"req-new",LIMITS,PLAN)

    def test_written_ledger_is_exactly_serialized_and_newline_terminated(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            reserve(path,"req-1",LIMITS,PLAN)
            raw=path.read_bytes()
            parsed=json.loads(raw)
            expected=(json.dumps(parsed,sort_keys=True,indent=2)+"\\n").encode("utf-8")
            self.assertEqual(raw,expected)
            self.assertLessEqual(len(raw),4*1024*1024)

    def test_settlement_preserves_exact_serialization(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"budget.json"
            reserve(path,"req-1",LIMITS,PLAN)
            settle(path,"req-1",ACTUAL)
            raw=path.read_bytes()
            self.assertEqual(raw,(json.dumps(json.loads(raw),sort_keys=True,indent=2)+"\\n").encode("utf-8"))

if __name__=="__main__":
    unittest.main()
