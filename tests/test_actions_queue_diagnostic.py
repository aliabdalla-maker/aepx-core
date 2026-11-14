"""Offline regression tests for the read-only Actions queue diagnostic."""
import unittest
import tempfile
import pathlib
import io
import contextlib
from unittest.mock import patch
from tools.diagnose_actions_queue import summarize, main

class QueueDiagnosticTests(unittest.TestCase):
    def test_counts_queued_and_completed(self):
        result = summarize([
            {"databaseId": 12, "name": "CI", "status": "queued", "createdAt": "2026-11-14"},
            {"databaseId": 13, "name": "Smoke", "status": "completed", "conclusion": "success"},
        ])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["statuses"], {"queued": 1, "completed": 1})
        self.assertEqual([x["id"] for x in result["not_started"]], [12])

    def test_other_unstarted_statuses(self):
        result = summarize([{"status": x} for x in ("waiting", "pending", "requested")])
        self.assertEqual(len(result["not_started"]), 3)

    def test_rejects_malformed_data(self):
        for invalid in ({}, [None], [{"status": None}]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    summarize(invalid)

    def test_missing_fixture_returns_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--input-json", "/nonexistent/aepx-queue.json"]), 2)

    def test_malformed_fixture_returns_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "invalid.json"
            path.write_text("{not json", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path)]), 2)

    def test_cli_invalid_json_returns_error(self):
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            run.return_value.stdout = "not json"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([]), 2)

    def test_cli_malformed_data_returns_error(self):
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            run.return_value.stdout = '{"not":"a list"}'
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([]), 2)

    def test_optional_monitoring_exit_on_queued(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "queued.json"
            path.write_text('[{"status":"queued","databaseId":17}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path)]), 0)
                self.assertEqual(main(["--input-json", str(path), "--fail-on-queued"]), 3)

    def test_optional_monitoring_exit_on_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "completed.json"
            path.write_text('[{"status":"completed","conclusion":"failure"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--fail-on-queued"]), 0)

    def test_require_success_rejects_failed_completed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "failed.json"
            path.write_text('[{"status":"completed","conclusion":"failure"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--require-success"]), 4)

    def test_require_success_rejects_queued_and_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            for payload in ('[{"status":"queued"}]', "[]"):
                path.write_text(payload, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--input-json", str(path), "--require-success"]), 4)

    def test_require_success_accepts_completed_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "passed.json"
            path.write_text('[{"status":"completed","conclusion":"success"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--require-success"]), 0)

    def test_completed_run_requires_conclusion(self):
        with self.assertRaisesRegex(ValueError, "lacks a conclusion"):
            summarize([{"status": "completed"}])

    def test_does_not_infer_root_cause(self):
        result = summarize([{"status": "queued"}])
        self.assertIn("cannot be determined", result["diagnosis"])

if __name__ == "__main__":
    unittest.main()
