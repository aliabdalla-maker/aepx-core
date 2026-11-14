"""Adversarial tests for offline 100-cycle report verification."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("cycle_verifier", pathlib.Path(__file__).resolve().parents[1] / "tools" / "verify_acceptance_cycle_report.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class CycleReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / "report.json"
        self.report = {
            "source_commit": "a" * 40, "workflow_run_id": "123",
            "requested": 2, "executed": 2, "all_passed": True,
            "independent_acceptance_established": False,
            "production_deployment_authorized": False,
            "runs": [
                {"iteration": i, "passed": True, "tests_executed": 42,
                 "return_code": 0, "elapsed_seconds": 0.1}
                for i in (1, 2)
            ],
        }

    def check(self):
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        return mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_digest_matches_exact_validated_bytes(self):
        import hashlib
        raw = json.dumps(self.report, sort_keys=True).encode("utf-8")
        self.path.write_bytes(raw)
        digests = []
        result = mod.verify(self.path, "a" * 40, "123", expected=2, digest_out=digests)
        self.assertEqual(result["executed"], 2)
        self.assertEqual(digests, [hashlib.sha256(raw).hexdigest()])

    def test_invalid_report_never_emits_digest(self):
        self.report["all_passed"] = False
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        digests = []
        with self.assertRaisesRegex(ValueError, "not all passed"):
            mod.verify(self.path, "a" * 40, "123", expected=2, digest_out=digests)
        self.assertEqual(digests, [])

    def test_rejects_invalid_expected_cycle_parameters(self):
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        for invalid in (0, -1, 101, True, 2.0, "2"):
            with self.subTest(expected=invalid):
                with self.assertRaisesRegex(ValueError, "expected cycle count"):
                    mod.verify(self.path, "a" * 40, "123", expected=invalid)

    def test_rejects_unsafe_minimum_test_threshold(self):
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        for invalid in (0, 41, True, 42.0, "42"):
            with self.subTest(minimum_tests=invalid):
                with self.assertRaisesRegex(ValueError, "minimum tests"):
                    mod.verify(self.path, "a" * 40, "123", expected=2, minimum_tests=invalid)

    def test_valid_report(self):
        self.assertEqual(self.check()["executed"], 2)

    def test_rejects_wrong_provenance(self):
        self.report["source_commit"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.check()

    def test_rejects_boolean_cycle_count(self):
        self.report["executed"] = True
        with self.assertRaisesRegex(ValueError, "cycle count"):
            self.check()

    def test_rejects_duplicate_cycle_number(self):
        self.report["runs"][1]["iteration"] = 1
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_insufficient_tests(self):
        self.report["runs"][0]["tests_executed"] = 41
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_forged_deployment_authorization(self):
        self.report["production_deployment_authorized"] = True
        with self.assertRaisesRegex(ValueError, "unauthorized"):
            self.check()

    def test_rejects_nonfinite_duration(self):
        self.report["runs"][0]["elapsed_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid JSON constant"):
            self.check()

    def test_rejects_duplicate_json_keys(self):
        self.path.write_text('{"source_commit":"a","source_commit":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_unexpected_root_fields(self):
        self.report["production_ready"] = True
        with self.assertRaisesRegex(ValueError, "report fields"):
            self.check()

    def test_rejects_unexpected_cycle_fields(self):
        self.report["runs"][0]["diagnostic_tail"] = "forged"
        with self.assertRaisesRegex(ValueError, "cycle 1 fields"):
            self.check()

    def test_rejects_malformed_commit_sha(self):
        self.report["source_commit"] = "not-a-sha"
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "commit SHA"):
            mod.verify(self.path, "not-a-sha", "123", expected=2)

    def test_rejects_malformed_workflow_run_id(self):
        self.report["workflow_run_id"] = "not-a-run"
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "run ID"):
            mod.verify(self.path, "a" * 40, "not-a-run", expected=2)

    def test_rejects_symlinked_report_input(self):
        original = pathlib.Path(self.tmp.name) / "original.json"
        original.write_text(json.dumps(self.report), encoding="utf-8")
        self.path.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "symlinked evidence"):
            mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_fails_closed_without_nofollow_support(self):
        from unittest.mock import patch
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        with patch.object(mod.os, "O_NOFOLLOW", None, create=True):
            with self.assertRaisesRegex(ValueError, "lacks required no-follow"):
                mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_fails_closed_with_zero_nofollow_flag(self):
        from unittest.mock import patch
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        with patch.object(mod.os, "O_NOFOLLOW", 0, create=True):
            with self.assertRaisesRegex(ValueError, "lacks required no-follow"):
                mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_fails_closed_with_boolean_nofollow_flag(self):
        from unittest.mock import patch
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        with patch.object(mod.os, "O_NOFOLLOW", True, create=True):
            with self.assertRaisesRegex(ValueError, "lacks required no-follow"):
                mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_fails_closed_without_close_on_exec_support(self):
        from unittest.mock import patch
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        for invalid in (None, 0, True):
            with self.subTest(invalid=invalid):
                with patch.object(mod.os, "O_CLOEXEC", invalid, create=True):
                    with self.assertRaisesRegex(ValueError, "lacks required close-on-exec"):
                        mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_fails_closed_without_nonblocking_support(self):
        from unittest.mock import patch
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        for invalid in (None, 0, True):
            with self.subTest(invalid=invalid):
                with patch.object(mod.os, "O_NONBLOCK", invalid, create=True):
                    with self.assertRaisesRegex(ValueError, "lacks required nonblocking"):
                        mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_fifo_swapped_before_open_without_blocking(self):
        from unittest.mock import patch
        import os
        if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
            self.skipTest("platform does not support nonblocking FIFO")
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        real_open = os.open

        def swap_to_fifo(path, flags, *args, **kwargs):
            self.assertTrue(flags & os.O_NONBLOCK)
            self.path.unlink()
            os.mkfifo(self.path)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(mod.os, "open", side_effect=swap_to_fifo):
            with self.assertRaisesRegex(ValueError, "unsafe or oversized opened evidence"):
                mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_symlink_swap_during_file_open(self):
        from unittest.mock import patch
        import os
        original = pathlib.Path(self.tmp.name) / "original.json"
        original.write_text(json.dumps(self.report), encoding="utf-8")
        self.path.write_text(json.dumps(self.report), encoding="utf-8")
        real_open = os.open

        def swapped_open(path, flags, *args, **kwargs):
            self.path.unlink()
            self.path.symlink_to(original)
            return real_open(path, flags, *args, **kwargs)

        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("platform does not support O_NOFOLLOW")
        with patch.object(mod.os, "open", side_effect=swapped_open):
            with self.assertRaises(OSError):
                mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_hardlinked_report_input(self):
        original = pathlib.Path(self.tmp.name) / "original.json"
        original.write_text(json.dumps(self.report), encoding="utf-8")
        import os
        os.link(original, self.path)
        with self.assertRaisesRegex(ValueError, "hardlinked evidence"):
            mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_oversized_report(self):
        self.path.write_text(" " * 2_000_001, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "oversized"):
            mod.verify(self.path, "a" * 40, "123", expected=2)

    def test_rejects_boolean_iteration(self):
        self.report["runs"][0]["iteration"] = True
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_boolean_return_code(self):
        self.report["runs"][0]["return_code"] = False
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_negative_duration(self):
        self.report["runs"][0]["elapsed_seconds"] = -0.01
        with self.assertRaisesRegex(ValueError, "invalid cycle"):
            self.check()

    def test_rejects_false_independent_acceptance_claim(self):
        self.report["independent_acceptance_established"] = True
        with self.assertRaisesRegex(ValueError, "independent acceptance"):
            self.check()
