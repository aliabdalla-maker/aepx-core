"""Offline request state tests."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("request_state",ROOT/"scripts/aepx_autonomous_request_state.py")
state=importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)

class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"requests.sqlite"
        self.conn=state.connect(self.path)
        state.create(self.conn,"req-1")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def advance(self,old,new):
        return state.transition(self.conn,"req-1",old,new,evidence="offline test evidence")

    def test_happy_path(self):
        self.advance("planned","reserved")
        self.advance("reserved","dispatched")
        self.advance("dispatched","settled")
        self.assertEqual(state.snapshot(self.conn)[0][1],"settled")

    def test_duplicate_request_denied(self):
        with self.assertRaises(sqlite3.IntegrityError):
            state.create(self.conn,"req-1")

    def test_stale_transition_denied(self):
        self.advance("planned","reserved")
        with self.assertRaises(state.StateDenied):
            self.advance("planned","reserved")

    def test_crash_recovery_is_uncertain(self):
        self.advance("planned","reserved")
        self.advance("reserved","dispatched")
        self.conn.close()
        self.conn=state.connect(self.path)
        self.assertEqual(state.recover_dispatched(self.conn),1)
        self.assertEqual(state.recover_dispatched(self.conn),0)
        self.assertEqual(state.snapshot(self.conn)[0][1],"uncertain")
        with self.assertRaises(state.StateDenied):
            self.advance("uncertain","dispatched")

    def test_attempt_increment_and_type_guard(self):
        result=state.transition(self.conn,"req-1","planned","reserved",
                                evidence="first attempt",increment_attempt=True)
        self.assertEqual(result["attempt"],1)
        with self.assertRaises(state.StateDenied):
            state.transition(self.conn,"req-1","reserved","dispatched",
                             evidence="invalid",increment_attempt="yes")

    def test_missing_evidence_denied(self):
        with self.assertRaises(state.StateDenied):
            state.transition(self.conn,"req-1","planned","reserved",evidence="")

    def test_event_audit(self):
        self.advance("planned","reserved")
        events=self.conn.execute("SELECT from_state,to_state,revision FROM request_events").fetchall()
        self.assertEqual(events,[("planned","reserved",1)])

if __name__=="__main__":
    unittest.main()
