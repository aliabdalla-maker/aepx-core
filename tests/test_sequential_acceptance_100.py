"""Runner safety tests; does not invoke real pytest suites."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from sequential_acceptance_100 import run

class SequentialAcceptanceTests(unittest.TestCase):
    def test_100_runs_are_strictly_sequential(self):
        calls=[]
        def fake_run(cmd,**kwargs):
            calls.append(len(calls)+1)
            return type("Result",(),{"returncode":0})()
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/"report.jsonl"
            with patch("sequential_acceptance_100.subprocess.run",side_effect=fake_run):
                self.assertEqual(run(100,["fake"],report),0)
            records=[json.loads(line) for line in report.read_text().splitlines()]
        self.assertEqual(calls,list(range(1,101)))
        self.assertEqual(len(records),100)
        self.assertTrue(all(x["outcome"]=="pass" for x in records))
    def test_fail_fast_and_report(self):
        codes=iter([0,0,3])
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/"report.jsonl"
            with patch("sequential_acceptance_100.subprocess.run",
                       side_effect=lambda *a,**kw:type("R",(),{"returncode":next(codes)})()):
                self.assertEqual(run(100,["fake"],report),3)
            records=[json.loads(x) for x in report.read_text().splitlines()]
        self.assertEqual(len(records),3)
        self.assertEqual(records[-1]["outcome"],"fail")
    def test_count_limits(self):
        with self.assertRaises(ValueError):
            run(101,["fake"],"unused.jsonl")
        with self.assertRaises(ValueError):
            run(0,["fake"],"unused.jsonl")
if __name__=="__main__":
    unittest.main()
