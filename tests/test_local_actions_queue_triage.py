"""Offline tests for runner-independent queue triage."""
import datetime
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "local-actions-queue-triage.py"
spec = importlib.util.spec_from_file_location("local_queue_triage", path)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


class QueueTriageTests(unittest.TestCase):
    def test_queued_age_and_status_counts(self):
        now = datetime.datetime(2026, 11, 13, 12, 0, tzinfo=datetime.timezone.utc)
        runs = [
            {"id": 1, "status": "queued", "created_at": "2026-11-13T11:30:00Z",
             "name": "ci", "html_url": "https://github.com/example/run/1"},
            {"id": 2, "status": "completed", "created_at": "2026-11-13T11:00:00Z"},
        ]
        report = triage.summarize(runs, now)
        self.assertEqual(report["sample_size"], 2)
        self.assertEqual(report["status_counts"], {"queued": 1, "completed": 1})
        self.assertEqual(report["conclusion_counts"], {"not_completed": 2})
        self.assertEqual(report["queued"][0]["age_minutes"], 30)

    def test_runner_evidence_is_bounded_and_read_only(self):
        requested = []
        def fake_fetch(url, token):
            requested.append(url)
            return {"jobs": [{"name": "build", "status": "queued",
                              "labels": ["ubuntu-latest"], "runner_id": None}]}
        queued = [{"id": i} for i in range(12)]
        evidence = triage.runner_evidence("org/repo", queued, "fake", fetch=fake_fetch)
        self.assertEqual(len(requested), 5)
        self.assertEqual(len(evidence), 5)
        self.assertFalse(evidence[0]["jobs"][0]["runner_assigned"])
        self.assertEqual(evidence[0]["jobs"][0]["labels"], ["ubuntu-latest"])
        self.assertTrue(all("/jobs?per_page=20" in url for url in requested))

    def test_runner_metadata_failure_is_reported(self):
        def failing_fetch(url, token):
            raise OSError("network unavailable")
        evidence = triage.runner_evidence("org/repo", [{"id": 42}], "fake",
                                         fetch=failing_fetch)
        self.assertEqual(evidence[0]["error_type"], "OSError")

    def test_completed_failures_without_jobs_are_reported(self):
        calls = []
        def fetch(url, token):
            calls.append(url)
            return {"jobs": []}
        runs = [{"id": i, "status": "completed", "conclusion": "failure",
                 "name": "gate"} for i in range(10)]
        evidence = triage.failed_before_jobs_evidence("org/repo", runs, "fake", fetch=fetch)
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(item["no_jobs_returned"] for item in evidence))
        self.assertTrue(all("triage_hint" in item for item in evidence))
        self.assertTrue(all(item["check_runs_url"] is None for item in evidence))

    def test_successful_runs_are_excluded_from_failure_sample(self):
        runs = [{"id": 1, "status": "completed", "conclusion": "success"}]
        self.assertEqual(triage.failed_before_jobs_evidence("org/repo", runs, "fake"), [])

    def test_queued_sample_is_bounded(self):
        now = datetime.datetime(2026, 11, 13, tzinfo=datetime.timezone.utc)
        runs = [{"id": i, "status": "queued", "created_at": "2026-11-13T00:00:00Z"}
                for i in range(50)]
        self.assertEqual(len(triage.summarize(runs, now)["queued"]), 20)


if __name__ == "__main__":
    unittest.main()
