"""Offline checkpoint regression tests; no model calls or network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aepx_pilot_checkpoint import append, initial, load, validate, exclusive_checkpoint_lock

class CheckpointTests(unittest.TestCase):
    def test_atomic_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            self.assertEqual(load(path), initial())
            append(path, {"pattern": "test_one.py", "status": "passed"})
            resumed = append(path, {"pattern": "test_two.py", "status": "failed"})
            self.assertEqual(len(resumed["attempts"]), 2)
            self.assertEqual(load(path)["attempts"][1]["number"], 2)
            self.assertFalse(resumed["release_approved"])

    def test_rejects_invalid_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                append(Path(directory) / "pilot.json",
                       {"pattern": "test_one.py", "status": "invented"})

    def test_rejects_unsafe_release_flags(self):
        state = initial()
        state["release_approved"] = True
        with self.assertRaises(ValueError):
            validate(state)

    def test_rejects_tampered_sequence(self):
        state = initial()
        state["attempts"] = [{"number": 2, "pattern": "test.py", "status": "passed"}]
        with self.assertRaises(ValueError):
            validate(state)

    def test_rejects_symlink_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "real.json"
            target.write_text(json.dumps(initial()), encoding="utf-8")
            link = Path(directory) / "link.json"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                append(link, {"pattern": "test.py", "status": "passed"})

    def test_rejects_concurrent_writer_without_lost_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            with exclusive_checkpoint_lock(path):
                with self.assertRaises(ValueError):
                    append(path, {"pattern": "test.py", "status": "passed"})
            self.assertEqual(len(load(path)["attempts"]), 0)
            self.assertFalse(path.with_name(path.name + ".lock").exists())
            self.assertEqual(len(append(path, {"pattern": "test.py", "status": "passed"})["attempts"]), 1)

    def test_rejects_abandoned_lock_until_operator_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            lock = path.with_name(path.name + ".lock")
            lock.mkdir()
            with self.assertRaises(ValueError):
                append(path, {"pattern": "test.py", "status": "passed"})
            self.assertTrue(lock.exists())
            lock.rmdir()
            self.assertEqual(len(append(path, {"pattern": "test.py", "status": "passed"})["attempts"]), 1)

if __name__ == "__main__":
    unittest.main()
