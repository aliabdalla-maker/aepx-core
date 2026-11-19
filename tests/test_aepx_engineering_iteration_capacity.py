"""Capacity regression for the full 10,000-iteration six-stage ledger."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_engineering_iteration_state import (
    MAX_BYTES,MAX_ITERATIONS,STAGES,validate,persist,load,TransitionDenied
)

class IterationCapacityTests(unittest.TestCase):
    def test_ten_thousand_completed_sha256_evidence_records_fit(self):
        evidence={stage:"sha256:"+("a"*64) for stage in STAGES}
        state={"version":1,"iterations":[
            {"number":i,"stage":"completed","evidence":evidence}
            for i in range(1,MAX_ITERATIONS+1)]}
        validate(state)
        payload=json.dumps(state,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(payload),MAX_BYTES)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/"iterations.json"
            persist(path,state)
            loaded=load(path)
            self.assertEqual(len(loaded["iterations"]),10000)
            self.assertEqual(loaded["iterations"][-1]["stage"],"completed")

    def test_worst_case_unicode_evidence_fits_byte_budget(self):
        evidence={stage:"🧪"*256 for stage in STAGES}
        state={"version":1,"iterations":[
            {"number":i,"stage":"completed","evidence":evidence}
            for i in range(1,MAX_ITERATIONS+1)]}
        validate(state)
        payload=json.dumps(state,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(payload),MAX_BYTES)

    def test_10001_iterations_rejected(self):
        evidence={stage:"sha256:"+("a"*64) for stage in STAGES}
        state={"version":1,"iterations":[
            {"number":i,"stage":"completed","evidence":evidence}
            for i in range(1,MAX_ITERATIONS+2)]}
        with self.assertRaises(TransitionDenied): validate(state)

if __name__=="__main__": unittest.main()
