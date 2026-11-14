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

    def test_malformed_evidence_entries_fail_closed(self):
        for bad in [None, 17, "not-an-object", {"path": 42, "sha256": "0" * 64}]:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "manifest.json"
                manifest.write_text(json.dumps({"milestones": [
                    {"id": "rls", "weight": 100, "evidence": [bad]}]}))
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_malformed_top_level_and_milestone_rejected(self):
        for payload in [None, [], {"milestones": [None]},
                        {"milestones": ["bad"]}, {"milestones": []}]:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "manifest.json"
                manifest.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_symlink_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.txt"
            target.write_bytes(b"proof")
            link = root / "proof.txt"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_oversized_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "large.bin").write_bytes(b"x" * (16 * 1024 * 1024 + 1))
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "large.bin", "sha256": "0" * 64,
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_manifest_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(" " * (1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_evidence_cardinality_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{}] * 101}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_milestone_cardinality_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": f"m{i}", "weight": 1, "evidence": []} for i in range(101)]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_symlinked_parent_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            (real / "proof.txt").write_bytes(b"proof")
            link = root / "linked"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "linked/proof.txt",
                              "sha256": hashlib.sha256(b"proof").hexdigest(),
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_ambiguous_evidence_path_syntax_fails_closed(self):
        for bad_path in ["../proof.txt", "./proof.txt", "dir//proof.txt",
                         "dir/../proof.txt", "dir\\\\proof.txt", "proof.txt\\u0000junk"]:
            with self.subTest(path=bad_path), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "proof.txt").write_bytes(b"proof")
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                    "evidence": [{"path": bad_path, "sha256": hashlib.sha256(b"proof").hexdigest(),
                                  "result": "pass"}]}]}))
                self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text('{"milestones":[],"milestones":[{"id":"rls","weight":100,"evidence":[]}]}')
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_nonfinite_json_constants_rejected(self):
        for constant in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "manifest.json"
                manifest.write_text('{"milestones":[{"id":"rls","weight":100,"evidence":[],"extra":'
                                    + constant + '}]}')
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_excessive_evidence_path_depth_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "/".join(["a"] * 65), "sha256": "0" * 64,
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_excessive_evidence_path_component_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "x" * 256, "sha256": "0" * 64,
                              "result": "pass"}]}]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_symlink_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "actual.json"
            target.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100, "evidence": []}]}))
            alias = root / "manifest.json"
            try:
                alias.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(OSError):
                verify(alias)

    def test_invalid_utf8_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_bytes(b"\\xff\\xfe")
            with self.assertRaises(UnicodeDecodeError):
                verify(manifest)

    def test_single_backslash_and_actual_nul_rejected(self):
        for path in ["folder\\\\proof.txt", "proof.txt" + chr(0) + "junk"]:
            with self.subTest(path=repr(path)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                    "evidence": [{"path": path, "sha256": "0" * 64, "result": "pass"}]}]}))
                self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

if __name__ == "__main__":
    unittest.main()
