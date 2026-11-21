"""Contract-only unit fixtures. All images and 'reviewers' below are FAKE test data.

PASS here never means real physical captures or actual human review happened.
"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from PIL import Image

from ocr_evolution.c221_audit import (validate_batch, evaluate_private_batch,
                                      write_private_report, ci_gate_status)


class C221AuditTests(unittest.TestCase):
    def make_batch(self, root, n=2):
        root = Path(root)
        (root / "reviews").mkdir(exist_ok=True)
        cases = []
        for i in range(n):
            name = f"scan_{i:02d}.png"
            img = root / name
            Image.new("RGB", (300, 120), (230 - i, 228, 220)).save(img)
            digest = hashlib.sha256(img.read_bytes()).hexdigest()
            review_files = []
            for reviewer in ("alice", "bob"):
                path = f"reviews/{reviewer}_{i:02d}.json"
                record = {
                    "case_id": f"scan_{i:02d}", "image_sha256": digest,
                    "reviewer_id": reviewer, "reviewed_at": "2026-11-22T08:00:00+09:00",
                    "visual_review_attested": True, "blind_review_attested": True,
                    "no_ocr_assistance_attested": True,
                    "transcription": "한글 테스트 예시",
                }
                (root / path).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                review_files.append(path)
            cases.append({
                "case_id": f"scan_{i:02d}", "category": "korean",
                "image": name, "sha256": digest,
                "capture_method": "camera_capture", "verified_physical_capture": True,
                "human_original_document_attested": True,
                "permission_attested": True, "license": "TEST ONLY NOT REAL",
                "source_group": f"source_{i:02d}", "review_files": review_files,
            })
        return {"schema_version": 1, "data_split": "development", "cases": cases}

    def edit_review(self, root, filename, **changes):
        path = Path(root) / filename
        content = json.loads(path.read_text(encoding="utf-8"))
        content.update(changes)
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    def test_two_case_contract_and_scoring(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root, 2)
            fake = Mock(return_value="한글 테스트 예시")
            result = evaluate_private_batch(batch, Path(root), ocr=fake)
            self.assertEqual(result["actual_captured_cases"], 2)
            self.assertEqual(result["source_groups"], 2)
            self.assertEqual(result["overall"]["cer"], 0)
            self.assertEqual(result["overall"]["wer"], 0)
            self.assertEqual(fake.call_count, 2)
            self.assertFalse(result["promotion_eligible"])
            self.assertNotIn("transcription", result["cases"][0])
            self.assertNotIn("한글 테스트", json.dumps(result, ensure_ascii=False))

    def test_ten_case_boundary(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root, 10)
            self.assertEqual(len(validate_batch(batch, Path(root))), 10)

    def test_one_and_eleven_block(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root, 11)
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))
            batch["cases"] = batch["cases"][:1]
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_missing_review_blocks_before_any_ocr(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            Path(root, batch["cases"][0]["review_files"][1]).unlink()
            fake = Mock()
            with self.assertRaises((ValueError, FileNotFoundError)):
                evaluate_private_batch(batch, Path(root), ocr=fake)
            fake.assert_not_called()

    def test_review_disagreement_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            self.edit_review(root, batch["cases"][0]["review_files"][1], transcription="서로 다른 텍스트")
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_ocr_assistance_claim_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            self.edit_review(root, batch["cases"][0]["review_files"][1], no_ocr_assistance_attested=False)
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_review_without_blindness_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            self.edit_review(root, batch["cases"][0]["review_files"][0], blind_review_attested=False)
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_wrong_digest_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            batch["cases"][0]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_same_source_group_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            batch["cases"][1]["source_group"] = batch["cases"][0]["source_group"]
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_simulated_capture_attestation_false_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            batch["cases"][0]["human_original_document_attested"] = False
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_missing_permission_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            batch["cases"][1]["permission_attested"] = False
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_distinct_reviewer_identity_required(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            self.edit_review(root, batch["cases"][0]["review_files"][1], reviewer_id="alice")
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_review_path_traversal_blocks(self):
        with TemporaryDirectory() as root:
            batch = self.make_batch(root)
            batch["cases"][0]["review_files"][0] = "../escape.json"
            with self.assertRaises(ValueError):
                validate_batch(batch, Path(root))

    def test_private_output_is_redacted_and_no_overwrite(self):
        with TemporaryDirectory() as root:
            out = Path(root) / "private" / "metrics.json"
            write_private_report(out, {"cer": 0.25, "wer": 0.5})
            self.assertEqual(json.loads(out.read_text())["cer"], 0.25)
            with self.assertRaises(FileExistsError):
                write_private_report(out, {"cer": 0})

    def test_ci_cannot_claim_real_two_human_measurements(self):
        gate = ci_gate_status()
        self.assertEqual(gate["real_physical_scans_with_confirmed_two_human_reviews"], 0)
        self.assertIsNone(gate["real_korean_scan_cer"])
        self.assertIn("BLOCKED_", gate["evaluation_gate"])


if __name__ == "__main__":
    unittest.main()
