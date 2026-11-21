"""Source-intake contract tests; fake images, not real paper or real human reviews."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from ocr_evolution.c221_source_intake import validate_queue, stage_verified_candidates


def example_case(source, index):
    data = source.read_bytes()
    with Image.open(source) as img:
        kind = img.format
        width, height = img.size
    return {
        "case_id": f"r_{index:02d}",
        "upstream_path": f"sample_{index}.jpg",
        "sha256": hashlib.sha256(data).hexdigest(),
        "decoded_format": kind, "width": width, "height": height,
        "image_bytes": len(data),
        "physical_capture_evidence": "NOT_VERIFIED",
        "human_review_evidence": "NOT_PROVIDED",
        "cer": None,"wer":None,
        "status": "BLOCKED_UNVERIFIED_PHYSICAL_ORIGIN_AND_HUMAN_GT",
    }


def example_queue(cases):
    return {
        "schema_version":1,
        "role":"actual_public_image_intake_unreviewed_not_a_real_scan_benchmark",
        "upstream_dataset":"HumynLabs/Korean_Receipts_Dataset",
        "upstream_commit":"a"*40,
        "upstream_license_claim":"CC-BY-4.0",
        "per_image_physical_capture_verified":False,
        "two_independent_human_full_transcripts":0,
        "independent_holdout":False,
        "promotion_eligible":False,
        "cases":cases,
    }


class C221SourceIntakeTests(unittest.TestCase):
    def fixture(self, folder):
        source=[]
        for n in (1,2):
            path=Path(folder)/f"src{n}.jpg"
            Image.new("RGB",(180+n,120+n),(200+n,210,220)).save(path)
            source.append(path)
        cases=[example_case(f,i) for i,f in enumerate(source,1)]
        return example_queue(cases),source

    def test_prior_real_public_artifact_is_explicitly_unreviewed(self):
        file=Path("benchmarks/c221_real_receipt_review_queue.json")
        doc=json.loads(file.read_text(encoding="utf-8"))
        revision, cases=validate_queue(doc)
        self.assertEqual(revision,"656cef561f4b8ff22e46d6785bc2807e78af99a1")
        self.assertEqual(len(cases),2)
        self.assertEqual(cases[0]["sha256"],
                         "164b8db862c88d020db6f3d0d2a456297d45cca20c3247022b0e88f3387ed19f")
        self.assertEqual(cases[1]["sha256"],
                         "5341ec7bae0ad68386a8bb75276c447d0b0ede5699ee3fb91d4b0920f698c6f8")

    def test_source_intake_local_with_exact_bytes(self):
        with TemporaryDirectory() as root:
            queue,source=self.fixture(root)
            paths={c["upstream_path"]:p for c,p in zip(queue["cases"],source)}
            called=[]
            def download(**kwargs):
                self.assertEqual(kwargs["revision"],"a"*40)
                called.append(kwargs["filename"])
                return str(paths[kwargs["filename"]])
            dest=Path(root)/"private-source"
            with patch.dict(os.environ,{"OCR_C221_EXTERNAL_DATA_CONSENT":"1"}):
                result=stage_verified_candidates(queue,dest,downloader=download)
            self.assertEqual(len(called),2)
            self.assertEqual(result["source_images_checked"],2)
            self.assertEqual(result["two_independent_full_human_transcriptions"],0)
            self.assertIsNone(result["actual_paper_scan_cer"])
            self.assertFalse(result["physical_capture_verified"])
            self.assertEqual(len(list(dest.glob("receipt_candidate_*"))),2)
            self.assertNotIn("transcription",(dest/"REVIEW_STATUS.json").read_text())

    def test_no_network_consent_blocks(self):
        with TemporaryDirectory() as root:
            queue,_=self.fixture(root)
            with patch.dict(os.environ,{"OCR_C221_EXTERNAL_DATA_CONSENT":"0"}):
                with self.assertRaises(RuntimeError):
                    stage_verified_candidates(queue,Path(root)/"unused",downloader=lambda **x:None)

    def test_download_hash_mismatch_blocks_all_writes(self):
        with TemporaryDirectory() as root:
            queue,source=self.fixture(root)
            fake=lambda **kwargs: str(source[1])  # case 1 gets case 2
            dest=Path(root)/"private-source"
            with patch.dict(os.environ,{"OCR_C221_EXTERNAL_DATA_CONSENT":"1"}):
                with self.assertRaises(ValueError):
                    stage_verified_candidates(queue,dest,downloader=fake)
            self.assertFalse(dest.exists())

    def test_duplicate_source_sha_rejected(self):
        with TemporaryDirectory() as root:
            queue,_=self.fixture(root)
            queue["cases"][1]["sha256"]=queue["cases"][0]["sha256"]
            with self.assertRaises(ValueError):
                validate_queue(queue)

    def test_cannot_auto_graduate_physical_capture(self):
        with TemporaryDirectory() as root:
            queue,_=self.fixture(root)
            queue["per_image_physical_capture_verified"]=True
            with self.assertRaises(ValueError):
                validate_queue(queue)
            queue["per_image_physical_capture_verified"]=False
            queue["cases"][0]["human_review_evidence"]="TWO_APPROVED"
            with self.assertRaises(ValueError):
                validate_queue(queue)

    def test_metrics_must_remain_null_until_real_humans(self):
        with TemporaryDirectory() as root:
            queue,_=self.fixture(root)
            queue["cases"][1]["cer"]=0
            with self.assertRaises(ValueError):
                validate_queue(queue)

    def test_cannot_write_in_git_checkout(self):
        with TemporaryDirectory() as root:
            queue,source=self.fixture(root)
            p=Path(root)/"repo"
            p.mkdir()
            (p/".git").mkdir()
            with patch.dict(os.environ,{"OCR_C221_EXTERNAL_DATA_CONSENT":"1"}):
                with self.assertRaises(ValueError):
                    stage_verified_candidates(queue,p/"ocr-data",downloader=lambda **kw:source[0])


if __name__=="__main__":
    unittest.main()
