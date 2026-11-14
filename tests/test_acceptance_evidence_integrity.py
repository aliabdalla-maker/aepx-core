import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools.verify_acceptance_evidence import verify


class EvidenceGateTests(unittest.TestCase):
    def test_valid_digest_is_not_independent_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_text("offline-test", encoding="utf-8")
            digest = hashlib.sha256(b"offline-test").hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "proof.txt", "sha256": digest, "result": "pass"}]}]}))
            result = verify(manifest)
            self.assertEqual(result["evidence_integrity_percent"], 100)
            self.assertEqual(result["independently_verified_percent"], 0)

    def test_missing_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "missing", "sha256": "0" * 64, "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "../outside", "sha256": "0" * 64, "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_weight_inflation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 101, "evidence": []}]}))
            with self.assertRaises(ValueError):
                verify(manifest)


    def test_duplicate_milestone_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": []},
                {"id": "rls", "weight": 50, "evidence": []}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_boolean_weight_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": True, "evidence": []}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_digest_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_text("changed", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "proof.txt", "sha256": hashlib.sha256(b"original").hexdigest(),
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

if __name__ == "__main__":
    unittest.main()
