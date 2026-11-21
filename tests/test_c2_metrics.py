import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import unicodedata

from ocr_evolution.metrics import edit_distance, evaluate_predictions, measure
from ocr_evolution.benchmark import load_manifest, segmentation_mode


def fixture(case_id, category, truth="안녕하세요", observed="안녕하세요"):
    return {"case_id": case_id, "category": category, "split": "development",
            "expected_text": truth, "observed_text": observed}


def dataset():
    return [fixture("k1", "korean"), fixture("t1", "table"), fixture("l1", "low_quality")]


class C2MetricTests(unittest.TestCase):
    def test_edit_distance_and_cer(self):
        self.assertEqual(edit_distance("가나", "가나라"), 1)
        self.assertEqual(measure("가나", "가나라")["char_errors"], 1)
        self.assertEqual(measure("가나", "가나라")["reference_chars"], 2)
        self.assertEqual(measure("하나 둘", "하나 셋")["word_errors"], 1)
        self.assertEqual(measure("하나 둘", "하나 셋")["reference_words"], 2)

    def test_unicode_nfc(self):
        decomposed = unicodedata.normalize("NFD", "한글")
        self.assertEqual(measure("한글", decomposed)["char_errors"], 0)

    def test_insertions_can_exceed_one(self):
        stats = measure("가", "가가가")
        self.assertEqual(stats["char_errors"], 2)
        self.assertEqual(stats["reference_chars"], 1)

    def test_micro_aggregation_by_category(self):
        cases = dataset()
        cases[0]["observed_text"] = "안녕하세"
        report = evaluate_predictions(cases)
        self.assertEqual(report["overall"]["count"], 3)
        self.assertGreater(report["overall"]["cer"], 0)
        self.assertEqual(report["by_category"]["table"]["cer"], 0)
        self.assertFalse(report["independent_holdout"])
        self.assertFalse(report["promotion_eligible"])

    def test_missing_or_duplicate_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate_predictions([])
        with self.assertRaises(ValueError):
            evaluate_predictions(dataset() + [dataset()[0]])
        with self.assertRaises(ValueError):
            evaluate_predictions(dataset()[:-1])
        with self.assertRaises(ValueError):
            measure("", "some text")
        with self.assertRaises(ValueError):
            measure(None, "some text")

    def test_non_dev_rejected(self):
        cases = dataset()
        cases[0]["split"] = "holdout"
        with self.assertRaises(ValueError):
            evaluate_predictions(cases)

    def test_table_segmentation_mode(self):
        self.assertEqual(segmentation_mode("korean"), 6)
        self.assertEqual(segmentation_mode("low_quality"), 6)
        self.assertEqual(segmentation_mode("table"), 11)
        with self.assertRaises(ValueError):
            segmentation_mode("unknown")

    def test_manifest_contract(self):
        manifest, source = load_manifest(Path("benchmarks/c2_synthetic_manifest.json"))
        self.assertEqual(len(manifest["cases"]), 6)
        self.assertEqual({c["category"] for c in manifest["cases"]},
                         {"korean", "table", "low_quality"})
        self.assertGreater(len(source), 10)
        self.assertEqual(manifest["split"], "development")

    def test_invalid_manifest_path_and_duplication(self):
        manifest, _ = load_manifest(Path("benchmarks/c2_synthetic_manifest.json"))
        with TemporaryDirectory() as folder:
            path = Path(folder) / "malicious.json"
            manifest["cases"][0]["case_id"] = "../escape"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(path)
            manifest["cases"][0]["case_id"] = manifest["cases"][1]["case_id"]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
