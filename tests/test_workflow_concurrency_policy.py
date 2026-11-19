"""Issue #370 regression: every push/PR workflow must bound its queue fan-out.

Without a concurrency group each commit enqueued ~100 jobs that were never
superseded, so stale branch runs starved newer acceptance evidence behind the
GitHub-hosted concurrent-job cap (thousands of queued runs on 2026-11-14).
"""
import glob
import os
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.y*ml")))
STANDARD_PREFIX = "${{ github.workflow }}-${{ github.event_name }}"
STANDARD_CANCEL = "${{ github.ref != 'refs/heads/master' }}"


def _load(path):
    with open(path, encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    on = doc.get(True, doc.get("on")) or {}
    if isinstance(on, str):
        on = {on: None}
    if isinstance(on, list):
        on = {key: None for key in on}
    return doc, set(on)


class WorkflowConcurrencyPolicyTests(unittest.TestCase):
    def test_workflows_exist(self):
        self.assertGreater(len(WORKFLOWS), 0)

    def test_push_and_pr_workflows_declare_ref_scoped_concurrency(self):
        problems = []
        for path in WORKFLOWS:
            doc, triggers = _load(path)
            if not triggers & {"push", "pull_request"}:
                continue
            name = os.path.basename(path)
            conc = doc.get("concurrency")
            if not isinstance(conc, dict) or not conc.get("group"):
                problems.append(f"{name}: no concurrency group")
                continue
            group = str(conc["group"])
            if "github.ref" not in group and "pull_request.number" not in group:
                problems.append(f"{name}: concurrency group is not ref scoped")
        self.assertEqual(problems, [])

    def test_standard_block_never_cancels_running_master_runs(self):
        seen = 0
        for path in WORKFLOWS:
            conc = _load(path)[0].get("concurrency")
            if isinstance(conc, dict) and str(conc.get("group", "")).startswith(STANDARD_PREFIX):
                seen += 1
                self.assertEqual(conc.get("cancel-in-progress"), STANDARD_CANCEL, os.path.basename(path))
        self.assertGreater(seen, 0)

    def test_hitl_acceptance_still_runs_on_every_push(self):
        doc, triggers = _load(os.path.join(ROOT, ".github", "workflows", "hitl-acceptance.yml"))
        self.assertIn("push", triggers)
        self.assertIsInstance(doc.get("concurrency"), dict)

    def test_dispatch_evidence_runs_are_not_cancelled(self):
        doc, _ = _load(os.path.join(ROOT, ".github", "workflows", "acceptance-50-cycles.yml"))
        self.assertIn("github.run_id", doc["concurrency"]["group"])
        self.assertFalse(doc["concurrency"]["cancel-in-progress"])


if __name__ == "__main__":
    unittest.main()
