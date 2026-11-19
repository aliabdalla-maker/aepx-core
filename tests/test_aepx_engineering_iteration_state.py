"""Offline engineering iteration state machine tests."""
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_engineering_iteration_state import (
    MAX_ITERATIONS, STAGES, TransitionDenied, advance, load, persist
)

class IterationStateTests(unittest.TestCase):
    def test_full_iteration_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iterations.json"
            state = load(path)
            for stage in STAGES:
                state = advance(state, number=1, stage=stage, evidence="sha256:" + stage)
            persist(path, state)
            self.assertEqual(load(path), state)
            self.assertEqual(state["iterations"][0]["stage"], "completed")
            state = advance(state, number=2, stage="requirements", evidence="sha256:new")
            self.assertEqual(len(state["iterations"]), 2)

    def test_no_skip_or_duplicate(self):
        state = advance(load(Path("/nonexistent/aepx-iteration-test.json")),
                        number=1, stage="requirements", evidence="sha256:req")
        for stage in ("requirements", "patch_proposed", "completed"):
            with self.subTest(stage=stage):
                with self.assertRaises(TransitionDenied):
                    advance(state, number=1, stage=stage, evidence="sha256:bad")

    def test_second_iteration_requires_completion(self):
        state = {"version":1, "iterations":[]}
        state = advance(state, number=1, stage="requirements", evidence="req")
        with self.assertRaises(TransitionDenied):
            advance(state, number=2, stage="requirements", evidence="req2")

    def test_missing_evidence_and_overflow(self):
        state = {"version":1, "iterations":[]}
        with self.assertRaises(TransitionDenied):
            advance(state, number=1, stage="requirements", evidence="")
        with self.assertRaises(TransitionDenied):
            advance(state, number=MAX_ITERATIONS+1, stage="requirements", evidence="ref")

if __name__=="__main__":
    unittest.main()
