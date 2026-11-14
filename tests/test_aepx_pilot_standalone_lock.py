"""Regression tests for standalone pilot checkpoint admission."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import aepx_autonomous_pilot as pilot
from aepx_pilot_checkpoint import exclusive_checkpoint_lock, load

PATTERN = "test_aepx_autonomous_checkpoint.py"

class StandaloneLockTests(unittest.TestCase):
    def invoke(self, checkpoint):
        argv = ["pilot", "--pattern", PATTERN, "--execute", "--checkpoint", str(checkpoint)]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            pilot.main()

    def test_competing_batch_blocks_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "pilot.json"
            lock = checkpoint.with_name(checkpoint.name + ".batch")
            with exclusive_checkpoint_lock(lock):
                with patch.object(pilot, "execute") as execute:
                    with self.assertRaisesRegex(ValueError, "locked"):
                        self.invoke(checkpoint)
                    execute.assert_not_called()

    def test_cap_blocks_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "pilot.json"
            with patch("aepx_pilot_checkpoint.load", return_value={"attempts":[None] * 10000}), \
                 patch.object(pilot, "execute") as execute:
                with self.assertRaisesRegex(ValueError, "iteration cap"):
                    self.invoke(checkpoint)
                execute.assert_not_called()

    def test_records_one_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "pilot.json"
            with patch.object(pilot, "execute", return_value={"pattern":PATTERN,"status":"passed"}):
                self.invoke(checkpoint)
            self.assertEqual(len(load(checkpoint)["attempts"]), 1)

if __name__ == "__main__":
    unittest.main()
