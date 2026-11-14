"""Offline bounded pilot tests using mocked test execution."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aepx_supervised_batch import run_batch
from aepx_pilot_checkpoint import load, exclusive_checkpoint_lock

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

    def test_rejects_cap_before_test_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            with patch("aepx_supervised_batch.load", return_value={"attempts": [None] * 10000}), \
                 patch("aepx_supervised_batch.execute") as execute:
                with self.assertRaisesRegex(ValueError, "iteration cap"):
                    run_batch(directory,path,PATTERN,1,10,enabled=True)
                execute.assert_not_called()

    def test_rejects_overflowing_batch_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            with patch("aepx_supervised_batch.load", return_value={"attempts": [None] * 9999}), \
                 patch("aepx_supervised_batch.execute") as execute:
                with self.assertRaisesRegex(ValueError, "iteration cap"):
                    run_batch(directory,path,PATTERN,2,10,enabled=True)
                execute.assert_not_called()

    def test_rejects_competing_batch_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            batch_lock = path.with_name(path.name + ".batch")
            with exclusive_checkpoint_lock(batch_lock):
                with patch("aepx_supervised_batch.execute") as execute:
                    with self.assertRaisesRegex(ValueError, "locked"):
                        run_batch(directory,path,PATTERN,1,10,enabled=True)
                    execute.assert_not_called()

if __name__ == "__main__":
    unittest.main()
