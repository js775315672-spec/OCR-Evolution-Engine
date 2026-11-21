"""Safety, table structure and public-corpus adapter tests without network access."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from ocr_evolution.table_structure import score_grid
from ocr_evolution.kdoc_public import choose_docs, score_table_text, score_verified_text
from ocr_evolution.real_corpus import load_corpus, evaluate_local_corpus


class StructureTests(TestCase):
    def test_perfect_structure(self):
        grid = [["품목", "수량"], ["사과", "2"]]
        result = score_grid(grid, grid)
        self.assertTrue(result["available"])
        self.assertEqual(result["cell"]["f1"], 1.0)
        self.assertEqual(result["adjacency"]["f1"], 1.0)

    def test_cell_swap_detected(self):
        reference = [["A", "B"], ["C", "D"]]
        predicted = [["B", "A"], ["C", "D"]]
        score = score_grid(reference, predicted)
        self.assertLess(score["cell"]["f1"], 1.0)
        self.assertLess(score["adjacency"]["f1"], 1.0)

    def test_flat_text_never_counts_as_structure(self):
        score = score_grid([["A", "B"]], None)
        self.assertFalse(score["available"])
        self.assertIsNone(score["adjacency"])

    def test_ragged_and_invalid_rejected(self):
        for bad in ([["A"], ["B", "C"]], [["A", 1]], "not a grid"):
            with self.assertRaises(ValueError):
                score_grid(bad, [])

    def test_extra_cells_penalized(self):
        result = score_grid([["A"]], [["A", "X"]])
        self.assertLess(result["cell"]["precision"], 1.0)


class PublicUnitTests(TestCase):
    def test_strict_verified_units(self):
        items = [{"type": "present", "checked": "verified", "text": "정부 안내"}]
        self.assertEqual(score_verified_text("새 정부 안내 자료", items)["matched"], 1)
        self.assertEqual(score_verified_text("새 정부 안개 자료", items)["matched"], 0)
        self.assertEqual(score_table_text("단가 3000", [{"type": "table", "checked": "verified", "cell": "3000"}])["matched"], 1)

    def test_unverified_unit_fails(self):
        with self.assertRaises(ValueError):
            score_verified_text("hi", [{"type": "present", "checked": "unverified", "text": "hi"}])

    def test_external_selector_requires_licenses_and_verification(self):
        rights = {
            "a.pdf": {"license": "이용허락범위 제한없음", "source_url": "https://example.org/a"},
            "b.pdf": {"license": "restricted", "source_url": "https://example.org/b"},
            "c.pdf": {"license": "이용허락범위 제한없음", "source_url": "https://example.org/c"},
        }
        groups = {"a.pdf": [{"right": "A"}], "b.pdf": [{"right": "B"}], "c.pdf": [{"right": "C"}]}
        self.assertEqual(choose_docs(rights, groups, groups, limit=1), ["a.pdf"])
        with self.assertRaises(ValueError):
            choose_docs(rights, groups, groups, limit=3)


class LocalRealCorpusTests(TestCase):
    def _make(self, folder):
        folder = Path(folder)
        Image.new("RGB", (100, 80), "white").save(folder / "img.png")
        digest = hashlib.sha256((folder / "img.png").read_bytes()).hexdigest()
        case = {"case_id": "real_01", "category": "low_quality",
                "capture_method": "camera_capture", "image": "img.png",
                "sha256": digest, "license": "evaluation permitted",
                "source_url": "https://example.org/source",
                "transcription": "실제 스캔 문장",
                "transcription_quality": "human_checked_full",
                "verified_snippets": ["실제 스캔"],
                "expected_table": [["칸1", "칸2"], ["칸3", "칸4"]]}
        path = folder / "manifest.json"
        path.write_text(json.dumps({"schema_version": 1, "public_split": "development",
                                    "cases": [case]}, ensure_ascii=False), encoding="utf-8")
        return case, path

    def test_human_full_truth_scores_cer_wer(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            with patch("ocr_evolution.real_corpus.subprocess.run") as fake:
                fake.return_value.stdout = "실제 스캔 문장"
                result = evaluate_local_corpus(manifest, Path(folder))
            self.assertEqual(result["full_transcriptions_count"], 1)
            self.assertEqual(result["overall_cer_wer"]["cer"], 0)
            self.assertFalse(result["cases"][0]["table_structure"]["available"])
            self.assertEqual(result["cases"][0]["verified_snippet_recall"]["matched"], 1)

    def test_sha_mismatch_blocks(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            case["sha256"] = "0" * 64
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development", "cases": [case]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_corpus(manifest, Path(folder))

    def test_unreviewed_truth_blocks(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            case.pop("transcription_quality")
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development", "cases": [case]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_corpus(manifest, Path(folder))

    def test_traversal_blocks(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            case["image"] = "../img.png"
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development", "cases": [case]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_corpus(manifest, Path(folder))

    def test_private_local_owner_attestation(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            case.pop("source_url")
            case["provenance_kind"] = "user_owned_local"
            case["permission_attested"] = True
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development",
                                            "cases": [case]}, ensure_ascii=False), encoding="utf-8")
            validated = load_corpus(manifest, Path(folder))
            self.assertEqual(len(validated), 1)
            case["permission_attested"] = False
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development",
                                            "cases": [case]}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_corpus(manifest, Path(folder))

    def test_sparse_truth_does_not_create_cer(self):
        with TemporaryDirectory() as folder:
            case, manifest = self._make(folder)
            case.pop("transcription")
            case.pop("transcription_quality")
            manifest.write_text(json.dumps({"schema_version": 1, "public_split": "development", "cases": [case]}), encoding="utf-8")
            with patch("ocr_evolution.real_corpus.subprocess.run") as fake:
                fake.return_value.stdout = "실제 스캔"
                result = evaluate_local_corpus(manifest, Path(folder))
            self.assertIsNone(result["overall_cer_wer"])
            self.assertIsNone(result["cases"][0]["cer"])


if __name__ == "__main__":
    import unittest
    unittest.main()
