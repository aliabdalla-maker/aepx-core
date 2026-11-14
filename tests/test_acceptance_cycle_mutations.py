"""60 adversarial mutations of offline acceptance evidence; no network or deployment."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "aepx_cycle_verifier_matrix",
    Path(__file__).resolve().parents[1] / "tools" / "verify_acceptance_cycle_report.py",
)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

SHA = "a" * 40
RUN_ID = "123"
BASE = {
    "source_commit": SHA,
    "workflow_run_id": RUN_ID,
    "requested": 2,
    "executed": 2,
    "all_passed": True,
    "independent_acceptance_established": False,
    "production_deployment_authorized": False,
    "runs": [
        {"iteration": i, "passed": True, "tests_executed": 42,
         "return_code": 0, "elapsed_seconds": 0.1}
        for i in (1, 2)
    ],
}


def mutations():
    cases = []
    for i in range(10):
        cases.append((f"unexpected_root_{i}", lambda r, i=i: r.update({f"untrusted_claim_{i}": True})))
    for i in range(10):
        cases.append((f"unexpected_cycle_{i}", lambda r, i=i: r["runs"][0].update({f"untrusted_cycle_{i}": True})))
    for i in range(10):
        cases.append((f"wrong_sha_{i}", lambda r, i=i: r.update({"source_commit": f"{i:040x}"})))
    for i in range(10):
        cases.append((f"wrong_run_id_{i}", lambda r, i=i: r.update({"workflow_run_id": str(1000 + i)})))
    for i, value in enumerate((0, -1, 1, 3, 4, 5, True, False, "2", 2.0)):
        cases.append((f"invalid_executed_{i}", lambda r, value=value: r.update({"executed": value})))
    for i, value in enumerate((-1, -0.1, 96, 100, 1e100, "0", None, True, False, float("nan"))):
        cases.append((f"invalid_elapsed_{i}", lambda r, value=value: r["runs"][0].update({"elapsed_seconds": value})))
    return cases


class MutationMatrixTests(unittest.TestCase):
    def test_all_sixty_adversarial_mutations_fail_closed(self):
        cases = mutations()
        self.assertEqual(len(cases), 60)
        self.assertEqual(len({name for name, _ in cases}), 60)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            for name, mutate in cases:
                with self.subTest(case=name):
                    report = copy.deepcopy(BASE)
                    mutate(report)
                    path.write_text(json.dumps(report), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        verifier.verify(path, SHA, RUN_ID, expected=2)

    def test_unmodified_baseline_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(BASE), encoding="utf-8")
            self.assertEqual(verifier.verify(path, SHA, RUN_ID, expected=2)["executed"], 2)


if __name__ == "__main__":
    unittest.main()
