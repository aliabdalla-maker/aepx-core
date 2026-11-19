"""Offline tests for read-only Actions queue diagnostics."""
import datetime
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "actions-queue-inspector.py"
spec = importlib.util.spec_from_file_location("queue_inspector", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW = datetime.datetime(2026, 11, 14, 12, tzinfo=datetime.timezone.utc)

def fixture(url, token):
    if url.endswith("/actions/runs?per_page=100"):
        return {"total_count": 2, "workflow_runs": [
            {"id": 42, "name": "HITL", "status": "queued",
             "created_at": "2026-11-14T11:30:00Z"},
            {"id": 43, "name": "CI", "status": "completed",
             "created_at": "2026-11-14T11:00:00Z"}]}
    if url.endswith("/42/jobs?per_page=100"):
        return {"total_count": 1, "jobs": [{"id": 420, "name": "postgres", "status": "queued",
                          "labels": ["ubuntu-latest"], "runner_id": None}]}
    raise AssertionError(url)

class QueueInspectorTests(unittest.TestCase):
    def test_queued_run_report_no_root_cause_guess(self):
        report = module.inspect("owner/repo", "token", get=fixture, now=NOW)
        self.assertEqual(report["queued"][0]["age_minutes"], 30)
        self.assertFalse(report["queued"][0]["jobs"][0]["runner_assigned"])
        self.assertEqual(report["status_counts"], {"queued": 1, "completed": 1})
        self.assertEqual(report["diagnosis"], "UNDETERMINED")
        self.assertFalse(report["release_approved"])
        self.assertFalse(report["sample_truncated"])
        self.assertEqual(report["total_count"], 2)
        self.assertEqual(report["queued"][0]["jobs"][0]["id"], 420)

    def test_invalid_job_id_blocks(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/jobs?" in url:
                result["jobs"][0]["id"] = True
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_invalid_runner_labels_block(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/jobs?" in url:
                result["jobs"][0]["labels"] = "ubuntu-latest"
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_truncated_run_sample_reported(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/runs?" in url:
                result["total_count"] = 200
            return result
        report = module.inspect("owner/repo", "token", get=fake, now=NOW)
        self.assertTrue(report["sample_truncated"])

    def test_truncated_job_evidence_blocks(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/jobs?" in url:
                result["total_count"] = 2
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_missing_total_count_blocks(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/runs?" in url:
                del result["total_count"]
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_rejects_malformed_repo_identifier(self):
        for repo in ["owner/repo/extra", "owner/repo?x=1", "../repo",
                     "owner//repo", "owner/repo#fragment"]:
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                module.inspect(repo, "token", get=fixture, now=NOW)

    def test_rejects_naive_clock(self):
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fixture,
                           now=datetime.datetime(2026, 11, 14, 12))

    def test_rejects_unknown_run_status(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/runs?" in url:
                result["workflow_runs"][0]["status"] = "not-a-status"
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_rejects_unknown_job_status(self):
        def fake(url, token):
            result = fixture(url, token)
            if "/jobs?" in url:
                result["jobs"][0]["status"] = "not-a-status"
            return result
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_invalid_run_payload_fails(self):
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=lambda url, token: {"workflow_runs": [None]}, now=NOW)

    def test_missing_job_metadata_fails(self):
        def fake(url, token):
            if "/jobs?" in url:
                return {"jobs": "invalid"}
            return fixture(url, token)
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

    def test_missing_timestamp_fails(self):
        def fake(url, token):
            if "/runs?" in url:
                return {"workflow_runs": [{"id": 1, "status": "queued"}]}
            return {}
        with self.assertRaises(ValueError):
            module.inspect("owner/repo", "token", get=fake, now=NOW)

if __name__ == "__main__":
    unittest.main()
