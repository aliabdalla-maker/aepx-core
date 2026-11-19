import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from sequential_acceptance_1000 import run_batches

class Sequential1000Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)/"reports"
        self.env=patch.dict(os.environ,{"AEPX_SEQUENTIAL_ACCEPTANCE_APPROVED":"yes"})
        self.env.start()
        self.addCleanup(self.env.stop)
    def fake_pass(self,args,**kwargs):
        count=int(args[args.index("--count")+1])
        report=Path(args[args.index("--report")+1])
        report.write_text("".join(json.dumps(dict(iteration=i,total=count,exit_code=0,
                         outcome="pass"))+"\n" for i in range(1,count+1)))
        return type("Result",(),{"returncode":0})()
    def test_all_1000_are_serial_and_verified(self):
        calls=[]
        def execute(args,**kwargs):
            calls.append(args)
            return self.fake_pass(args,**kwargs)
        with patch("sequential_acceptance_1000.subprocess.run",side_effect=execute):
            self.assertEqual(run_batches(report_dir=self.dir),0)
        self.assertEqual(len(calls),10)
        self.assertEqual([Path(x[-1]).name for x in calls],
                         [f"batch-{i:02d}.jsonl" for i in range(1,11)])
        self.assertEqual(len((self.dir/"summary.jsonl").read_text().splitlines()),10)
    def test_missing_records_fail_closed(self):
        with patch("sequential_acceptance_1000.subprocess.run",
                   return_value=type("Result",(),{"returncode":0})()) as mocked:
            self.assertEqual(run_batches(report_dir=self.dir),1)
            self.assertEqual(mocked.call_count,1)
    def test_first_failed_batch_stops(self):
        with patch("sequential_acceptance_1000.subprocess.run",
                   return_value=type("Result",(),{"returncode":1})()) as mocked:
            self.assertEqual(run_batches(report_dir=self.dir),1)
            self.assertEqual(mocked.call_count,1)
    def test_existing_reports_cannot_be_overwritten(self):
        self.dir.mkdir(parents=True)
        (self.dir/"summary.jsonl").write_text("old")
        with self.assertRaises(FileExistsError):
            run_batches(report_dir=self.dir)
    def test_approval_required(self):
        os.environ.pop("AEPX_SEQUENTIAL_ACCEPTANCE_APPROVED",None)
        with self.assertRaises(PermissionError):
            run_batches(report_dir=self.dir)
if __name__=="__main__":
    unittest.main()
