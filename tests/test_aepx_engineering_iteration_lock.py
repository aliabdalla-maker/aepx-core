"""Fail-closed single-host engineering ledger serialization tests."""
import tempfile
import unittest
from pathlib import Path
from scripts.aepx_engineering_iteration_state import advance_locked, TransitionDenied

class LockedIterationTests(unittest.TestCase):
    def test_atomic_serialized_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"iterations.json"
            a=advance_locked(path,number=1,stage="requirements",evidence="req")
            self.assertEqual(a["iterations"][0]["stage"],"requirements")
            b=advance_locked(path,number=1,stage="design",evidence="design")
            self.assertEqual(b["iterations"][0]["stage"],"design")
            with self.assertRaises(TransitionDenied):
                advance_locked(path,number=1,stage="completed",evidence="skip")

    def test_existing_lock_denies_without_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"iterations.json"
            lock=Path(str(path)+".lock")
            lock.mkdir()
            with self.assertRaises(ValueError):
                advance_locked(path,number=1,stage="requirements",evidence="req")
            self.assertFalse(path.exists())

    def test_symlink_destination_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"real.json"
            target.write_text('{"version":1,"iterations":[]}')
            link=Path(tmp)/"alias.json"
            link.symlink_to(target)
            with self.assertRaises(TransitionDenied):
                advance_locked(link,number=1,stage="requirements",evidence="req")

if __name__=="__main__":
    unittest.main()
