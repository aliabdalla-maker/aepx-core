import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
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
            with self.assertRaises(ValueError):
                verify(manifest)

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
                with self.assertRaises(ValueError):
                    verify(manifest)

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
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_excessive_evidence_path_component_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [{"path": "x" * 256, "sha256": "0" * 64,
                              "result": "pass"}]}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

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
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_duplicate_evidence_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            evidence = {"path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                        "result": "pass"}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{"id": "rls", "weight": 100,
                "evidence": [evidence, evidence]}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_evidence_reuse_across_milestones_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            entry = {"path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                     "result": "pass"}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [entry]},
                {"id": "oidc", "weight": 50, "evidence": [entry]}]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_manifest_mutation_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 100, "evidence": []}]}))
            original_read = os.read
            modified = False

            def mutating_read(fd, size):
                nonlocal modified
                chunk = original_read(fd, size)
                if chunk and not modified:
                    modified = True
                    with manifest.open("ab") as output:
                        output.write(b" ")
                return chunk

            with patch("tools.verify_acceptance_evidence.os.read", side_effect=mutating_read):
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_unknown_schema_fields_rejected(self):
        valid = {"milestones": [{"id": "rls", "weight": 100, "evidence": []}]}
        variants = [
            {**valid, "independently_verified_percent": 100},
            {"milestones": [{"id": "rls", "weight": 100, "evidence": [],
                              "independently_verified": True}]},
            {"milestones": [{"id": "rls", "weight": 100, "evidence": [
                {"path": "proof.txt", "sha256": "0" * 64, "result": "pass",
                 "trusted": True}]}]},
        ]
        for payload in variants:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "manifest.json"
                manifest.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    verify(manifest)

    def test_hard_linked_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_bytes(b"hardlink-test")
            linked = root / "proof.txt"
            os.link(source, linked)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": [{
                    "path": "proof.txt",
                    "sha256": hashlib.sha256(b"hardlink-test").hexdigest(),
                    "result": "pass"
                }]
            }]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_hard_link_created_during_hashing_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = root / "proof.txt"
            proof.write_bytes(b"proof")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": [{
                    "path": "proof.txt",
                    "sha256": hashlib.sha256(b"proof").hexdigest(),
                    "result": "pass"
                }]
            }]}))
            original_read = os.read
            linked = False

            def linking_read(fd, size):
                nonlocal linked
                chunk = original_read(fd, size)
                if chunk == b"proof" and not linked:
                    linked = True
                    os.link(proof, root / "alias.txt")
                return chunk

            with patch("tools.verify_acceptance_evidence.os.read", side_effect=linking_read):
                self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)
            self.assertTrue(linked)

    def test_hard_linked_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": []
            }]}))
            os.link(manifest, root / "manifest-alias.json")
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_manifest_hard_link_created_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": []
            }]}))
            original_read = os.read
            linked = False

            def linking_read(fd, size):
                nonlocal linked
                chunk = original_read(fd, size)
                if chunk and not linked:
                    linked = True
                    os.link(manifest, root / "manifest-alias.json")
                return chunk

            with patch("tools.verify_acceptance_evidence.os.read", side_effect=linking_read):
                with self.assertRaises(ValueError):
                    verify(manifest)
            self.assertTrue(linked)

    def test_manifest_path_with_nul_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / ("manifest" + chr(0) + ".json")
            with self.assertRaises(ValueError):
                verify(invalid)

    def test_invalid_path_with_malformed_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": [{
                    "path": "../outside.txt", "sha256": "not-a-digest", "result": "pass"
                }]
            }]}))
            with self.assertRaises(ValueError):
                verify(manifest)

    def test_unknown_evidence_result_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            for invalid in ("skipped", "pending", "", None, True, 1):
                with self.subTest(result=invalid):
                    manifest = root / "manifest.json"
                    manifest.write_text(json.dumps({"milestones": [{
                        "id": "rls", "weight": 100, "evidence": [{
                            "path": "proof.txt",
                            "sha256": hashlib.sha256(b"proof").hexdigest(),
                            "result": invalid
                        }]
                    }]}))
                    with self.assertRaises(ValueError):
                        verify(manifest)

    def test_explicit_failed_evidence_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": [{
                    "path": "proof.txt",
                    "sha256": hashlib.sha256(b"proof").hexdigest(),
                    "result": "fail"
                }]
            }]}))
            self.assertEqual(verify(manifest)["evidence_integrity_percent"], 0)

    def test_explicit_failed_evidence_does_not_access_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [{
                "id": "rls", "weight": 100, "evidence": [{
                    "path": "missing.txt", "sha256": "0" * 64, "result": "fail"
                }]
            }]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("failed evidence must not be opened")):
                result = verify(manifest)
            self.assertEqual(result["evidence_integrity_percent"], 0)

    def test_invalid_weight_allocation_does_not_read_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [{
                    "path": "proof.txt",
                    "sha256": hashlib.sha256(b"proof").hexdigest(),
                    "result": "pass"
                }]},
                {"id": "oidc", "weight": 49, "evidence": []}
            ]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("invalid allocation must not read evidence")):
                with self.assertRaisesRegex(ValueError, "weights must sum to 100"):
                    verify(manifest)

    def test_duplicate_milestone_ids_do_not_read_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            entry = {"path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                     "result": "pass"}
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [entry]},
                {"id": "rls", "weight": 50, "evidence": []}
            ]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("duplicate milestone must not read evidence")):
                with self.assertRaisesRegex(ValueError, "duplicate milestone id"):
                    verify(manifest)

    def test_later_invalid_evidence_schema_blocks_all_file_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [{
                    "path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                    "result": "pass"
                }]},
                {"id": "oidc", "weight": 50, "evidence": [{
                    "path": "../escape", "sha256": "bad", "result": "pass"
                }]}
            ]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("invalid manifest must not read evidence")):
                with self.assertRaisesRegex(ValueError, "invalid evidence path components"):
                    verify(manifest)

    def test_later_duplicate_evidence_path_blocks_all_file_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            entry = {"path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                     "result": "pass"}
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [entry]},
                {"id": "oidc", "weight": 50, "evidence": [entry]}
            ]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("duplicate path must not read evidence")):
                with self.assertRaisesRegex(ValueError, "duplicate evidence path"):
                    verify(manifest)

    def test_later_invalid_result_blocks_earlier_file_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_bytes(b"proof")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"milestones": [
                {"id": "rls", "weight": 50, "evidence": [{
                    "path": "proof.txt", "sha256": hashlib.sha256(b"proof").hexdigest(),
                    "result": "pass"
                }]},
                {"id": "oidc", "weight": 50, "evidence": [{
                    "path": "missing.txt", "sha256": "0" * 64, "result": "pending"
                }]}
            ]}))
            with patch("tools.verify_acceptance_evidence.safe_digest",
                       side_effect=AssertionError("invalid result must not read evidence")):
                with self.assertRaisesRegex(ValueError, "evidence result must be pass or fail"):
                    verify(manifest)

if __name__ == "__main__":
    unittest.main()
