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
            path.write_text('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"completed","conclusion":"failure"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--fail-on-queued"]), 0)

    def test_require_success_rejects_failed_completed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "failed.json"
            path.write_text('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"completed","conclusion":"failure"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--require-workflow", "CI", "--require-success"]), 4)

    def test_require_success_rejects_queued_and_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            for payload in ('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"queued"}]', "[]"):
                path.write_text(payload, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--input-json", str(path), "--head-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--require-workflow", "CI", "--require-success"]), 4 if payload != "[]" else 5)

    def test_require_success_accepts_completed_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "passed.json"
            path.write_text('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"completed","conclusion":"success"}]', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--require-workflow", "CI", "--require-success"]), 0)

    def test_completed_run_requires_conclusion(self):
        with self.assertRaisesRegex(ValueError, "lacks a conclusion"):
            summarize([{"status": "completed"}])

    def test_head_sha_scope_excludes_other_commits(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            path.write_text('[{"name":"CI","status":"completed","conclusion":"success","headSha":"' +
                            sha + '"},{"status":"queued","headSha":"' + "b" * 40 + '"}]',
                            encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", sha,
                                       "--require-workflow", "CI", "--require-success"]), 0)
                self.assertEqual(main(["--input-json", str(path), "--head-sha", "c" * 40,
                                       "--require-workflow", "CI", "--require-success"]), 5)

    def test_head_sha_scope_rejects_malformed_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            path.write_text('[null]', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path),
                                       "--head-sha", "a" * 40]), 2)

    def test_required_workflow_coverage_rejects_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            path.write_text('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"completed","conclusion":"success"}]',
                            encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--require-success",
                                       "--require-workflow", "CI",
                                       "--require-workflow", "AEP-X fast offline acceptance smoke"]), 5)

    def test_required_workflow_coverage_accepts_present(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            path.write_text('[{"name":"CI","headSha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"completed","conclusion":"success"}]',
                            encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--require-success",
                                       "--require-workflow", "CI"]), 0)

    def test_head_sha_filter_rejects_missing_or_invalid_record_sha(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            for bad in ('{"name":"CI","status":"queued"}',
                        '{"name":"CI","headSha":null,"status":"queued"}',
                        '{"name":"CI","headSha":"bad","status":"queued"}'):
                with self.subTest(bad=bad):
                    path.write_text("[" + bad + "]", encoding="utf-8")
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(main(["--input-json", str(path),
                                               "--head-sha", sha]), 2)

    def test_head_sha_filter_accepts_uppercase_hex(self):
        sha = "abcdef" * 6 + "abcd"
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "runs.json"
            path.write_text(
                '[{"name":"CI","headSha":"' + sha +
                '","status":"completed","conclusion":"success"}]',
                encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input-json", str(path), "--head-sha", sha.upper(),
                                       "--require-workflow", "CI", "--require-success"]), 0)

    def test_truncation_checked_before_sha_filter(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "mixed.json"
            path.write_text(
                '[{"name":"CI","headSha":"' + sha +
                '","status":"completed","conclusion":"success"},'
                '{"name":"CI","headSha":"' + "b" * 40 +
                '","status":"completed","conclusion":"success"}]',
                encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--input-json", str(path), "--limit", "2",
                                           "--head-sha", sha, "--require-workflow", "CI",
                                           "--require-success"]), 6)

    def test_strict_snapshot_limit_is_not_accepted_as_complete(self):
        sha = "a" * 40
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            run.return_value.stdout = (
                '[{"name":"CI","headSha":"' + sha +
                '","status":"completed","conclusion":"success"}]'
            )
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--head-sha", sha, "--limit", "1",
                                           "--require-workflow", "CI",
                                           "--require-success"]), 6)

    def test_blank_required_workflow_rejected_before_cli(self):
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            for name in ("", "  "):
                with self.subTest(name=name):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as failure:
                            main(["--require-workflow", name])
                    self.assertEqual(failure.exception.code, 2)
            run.assert_not_called()

    def test_invalid_commit_rejected_before_cli_invocation(self):
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            for invalid in ("bad", "g" * 40, "a" * 39):
                with self.subTest(invalid=invalid):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as failure:
                            main(["--head-sha", invalid])
                    self.assertEqual(failure.exception.code, 2)
            run.assert_not_called()

    def test_cli_filters_commit_before_result_limit(self):
        sha = "a" * 40
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            run.return_value.stdout = (
                '[{"name":"CI","headSha":"' + sha +
                '","status":"completed","conclusion":"success"}]'
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--head-sha", sha, "--limit", "2",
                                       "--require-workflow", "CI",
                                       "--require-success"]), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[-2:], ["--commit", sha])
            self.assertIn("--limit", command)

    def test_strict_mode_requires_explicit_scope(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as missing_scope:
                main(["--require-success"])
            self.assertEqual(missing_scope.exception.code, 2)
            with self.assertRaises(SystemExit) as missing_workflow:
                main(["--require-success", "--head-sha", "a" * 40])
            self.assertEqual(missing_workflow.exception.code, 2)

    def test_rejects_unknown_status(self):
        with self.assertRaisesRegex(ValueError, "unknown workflow run status"):
            summarize([{"status": "mystery"}])

    def test_rejects_duplicate_run_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate workflow run ID"):
            summarize([{"databaseId": 10, "status": "queued"},
                       {"databaseId": 10, "status": "completed", "conclusion": "success"}])

    def test_rejects_invalid_run_id_and_name(self):
        for run in ({"databaseId": True, "status": "queued"},
                    {"databaseId": -1, "status": "queued"},
                    {"name": " ", "status": "queued"}):
            with self.subTest(run=run):
                with self.assertRaises(ValueError):
                    summarize([run])

    def test_strict_workflow_coverage_rejects_unnamed_run(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "unnamed.json"
            path.write_text('[{"headSha":"' + sha +
                            '","status":"completed","conclusion":"success"}]',
                            encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--input-json", str(path),
                                           "--head-sha", sha, "--require-workflow", "CI",
                                           "--require-success"]), 2)

    def test_cli_normalizes_uppercase_sha_before_query(self):
        sha = "abcdef" * 6 + "abcd"
        with patch("tools.diagnose_actions_queue.subprocess.run") as run:
            run.return_value.stdout = "[]"
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--head-sha", sha.upper()])
            self.assertEqual(run.call_args.args[0][-2:], ["--commit", sha])

    def test_does_not_infer_root_cause(self):
        result = summarize([{"status": "queued"}])
        self.assertIn("cannot be determined", result["diagnosis"])

if __name__ == "__main__":
    unittest.main()
