"""Offline tests; no provider calls, no database and no dispatch enablement."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/governance"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.hitl_isolated_callback import run_isolated_callback, CallbackIsolationError

ALLOW = frozenset({
    "hitl_callback_fixtures:succeeds",
    "hitl_callback_fixtures:rejects",
    "hitl_callback_fixtures:hangs",
    "hitl_callback_fixtures:fails",
    "hitl_callback_fixtures:crashes",
})

class TestIsolatedCallback(unittest.TestCase):
    def run_adapter(self, name, timeout=3):
        return run_isolated_callback(entrypoint="hitl_callback_fixtures:" + name,
                                     arguments={}, allowed_entrypoints=ALLOW,
                                     timeout_seconds=timeout)

    def test_success(self):
        self.assertIs(self.run_adapter("succeeds"), True)

    def test_explicit_rejection(self):
        self.assertIs(self.run_adapter("rejects"), False)

    def test_timeout_is_uncertain_not_success(self):
        with self.assertRaisesRegex(CallbackIsolationError, "outcome uncertain"):
            self.run_adapter("hangs", timeout=0.2)

    def test_failure_is_uncertain(self):
        with self.assertRaisesRegex(CallbackIsolationError, "^callback failed: outcome uncertain$"):
            self.run_adapter("fails")

    def test_abrupt_process_crash_is_uncertain(self):
        with self.assertRaises(CallbackIsolationError):
            self.run_adapter("crashes", timeout=2)

    def test_timeout_is_bounded(self):
        import time
        started = time.monotonic()
        with self.assertRaises(CallbackIsolationError):
            self.run_adapter("hangs", timeout=0.2)
        self.assertLess(time.monotonic() - started, 4)

    def test_non_allowlisted_adapter_rejected(self):
        with self.assertRaises(CallbackIsolationError):
            run_isolated_callback(entrypoint="os:system", arguments={"command": "echo unsafe"},
                                  allowed_entrypoints=ALLOW)

    def test_invalid_timeout_rejected(self):
        with self.assertRaises(ValueError):
            self.run_adapter("succeeds", timeout=True)
