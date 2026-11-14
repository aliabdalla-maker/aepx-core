"""Offline regression checks for exact-SHA hosted release evidence."""
import importlib.util
import unittest
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "scripts" / "github-release-evidence.py"
spec = importlib.util.spec_from_file_location("github_release_evidence", p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = "a" * 40

def run(path, id=1, status="completed", conclusion="success", sha=SHA):
    return {"id": id, "run_attempt": 1, "created_at": "2026-11-14T00:00:00Z",
            "head_sha": sha, "path": path, "status": status, "conclusion": conclusion}

class ReleaseEvidenceTests(unittest.TestCase):
    def test_all_success_is_evidence_not_approval(self):
        runs = [run(path, i + 1) for i, path in enumerate(module.REQUIRED)]
        self.assertEqual(module.evaluate(runs, SHA), [])

    def test_missing_required_check_blocks(self):
        self.assertEqual(len(module.evaluate([], SHA)), len(module.REQUIRED))

    def test_queued_check_blocks(self):
        runs = [run(path, i + 1) for i, path in enumerate(module.REQUIRED)]
        runs[0]["status"], runs[0]["conclusion"] = "queued", None
        self.assertTrue(module.evaluate(runs, SHA))

    def test_wrong_sha_blocks(self):
        runs = [run(path, i + 1, sha="b" * 40) for i, path in enumerate(module.REQUIRED)]
        self.assertEqual(len(module.evaluate(runs, SHA)), len(module.REQUIRED))

    def test_newer_failure_overrides_old_success(self):
        runs = [run(path, i + 1) for i, path in enumerate(module.REQUIRED)]
        runs.append(run(module.REQUIRED[0], 100, "completed", "failure"))
        self.assertTrue(module.evaluate(runs, SHA))

    def test_duplicate_run_id_blocks(self):
        runs = [run(path, i + 1) for i, path in enumerate(module.REQUIRED)]
        runs.append(run(module.REQUIRED[0], 1))
        self.assertTrue(module.evaluate(runs, SHA))

    def test_invalid_metadata_blocks(self):
        for key, value in [("id", 0), ("id", True), ("run_attempt", 0),
                           ("run_attempt", True), ("created_at", "invalid"),
                           ("created_at", "2026-11-14T00:00:00")]:
            runs = [run(path, i + 1) for i, path in enumerate(module.REQUIRED)]
            runs[0][key] = value
            self.assertTrue(module.evaluate(runs, SHA))

    def test_malformed_collections_block(self):
        self.assertTrue(module.evaluate([None], SHA))
        self.assertTrue(module.evaluate({"invalid": True}, SHA))
        for payload in [None, [], {"workflow_runs": [None]},
                        {"workflow_runs": "bad"}]:
            with self.assertRaises(ValueError):
                module.fetch_runs("owner/repo", SHA, "token", fetch=lambda url: payload)

    def test_pagination_fail_closed(self):
        def fake(url):
            return {"workflow_runs": [run(module.REQUIRED[0])] * 100}
        with self.assertRaises(ValueError):
            module.fetch_runs("owner/repo", SHA, "token", fetch=fake)

if __name__ == "__main__":
    unittest.main()
