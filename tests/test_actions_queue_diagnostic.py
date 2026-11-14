"""Offline regression tests for the read-only Actions queue diagnostic."""
import unittest
from tools.diagnose_actions_queue import summarize

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

    def test_does_not_infer_root_cause(self):
        result = summarize([{"status": "queued"}])
        self.assertIn("cannot be determined", result["diagnosis"])

if __name__ == "__main__":
    unittest.main()
