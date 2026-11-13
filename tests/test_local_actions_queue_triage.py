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
        self.assertEqual(report["queued"][0]["age_minutes"], 30)

    def test_queued_sample_is_bounded(self):
        now = datetime.datetime(2026, 11, 13, tzinfo=datetime.timezone.utc)
        runs = [{"id": i, "status": "queued", "created_at": "2026-11-13T00:00:00Z"}
                for i in range(50)]
        self.assertEqual(len(triage.summarize(runs, now)["queued"]), 20)


if __name__ == "__main__":
    unittest.main()
