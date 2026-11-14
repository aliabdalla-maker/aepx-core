"""Offline bounded pilot tests using mocked test execution."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aepx_supervised_batch import run_batch
from aepx_pilot_checkpoint import load

PATTERN = "test_aepx_autonomous_checkpoint.py"

class BatchTests(unittest.TestCase):
    def test_records_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            with patch("aepx_supervised_batch.execute", return_value={"pattern": PATTERN,"status":"passed"}):
                first = run_batch(directory,path,PATTERN,2,10,enabled=True)
                second = run_batch(directory,path,PATTERN,1,10,enabled=True)
            self.assertEqual(first["recorded"], 2)
            self.assertEqual(second["initial_attempts"], 2)
            self.assertEqual(len(load(path)["attempts"]), 3)

    def test_stops_on_first_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            with patch("aepx_supervised_batch.execute", return_value={"pattern": PATTERN,"status":"failed"}) as execute:
                report = run_batch(directory,path,PATTERN,100,10,enabled=True)
            self.assertEqual(report["stopped"], "failure")
            self.assertEqual(report["recorded"], 1)
            execute.assert_called_once()

    def test_requires_explicit_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_batch(directory,Path(directory)/"checkpoint.json",PATTERN,1,10)

    def test_rejects_unbounded_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_batch(directory,Path(directory)/"checkpoint.json",PATTERN,101,10,enabled=True)

if __name__ == "__main__":
    unittest.main()
