import hashlib
import json
import os
import tarfile
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from ocr_evolution.c22_review import adjudicate, build_local_manifest
from ocr_evolution.c22_public import (GIST_CASES, RECEIPT_FILES, GIST_REPO, RECEIPT_REPO,
                                       immutable_revision, inspect_image, run_public, find_publisher_asset_paths,
                                       extract_selected_crop_members, archive_byte_budget)


class C22ReviewTests(unittest.TestCase):
    SHA = "a" * 64

    def reviews(self, first="가나다 라마", second="가나다 라마"):
        return [
            {"reviewer_id": "human_one", "image_sha256": self.SHA,
             "transcription": first, "visual_review_attested": True,
             "reviewed_at": "2026-11-22T08:00:00+09:00"},
            {"reviewer_id": "human_two", "image_sha256": self.SHA,
             "transcription": second, "visual_review_attested": True,
             "reviewed_at": "2026-11-22T08:05:00+09:00"},
        ]

    def test_two_distinct_matching_reviews_are_required(self):
        result = adjudicate(self.SHA, self.reviews())
        self.assertEqual(result["text"], "가나다 라마")
        self.assertEqual(len(result["reviewer_ids"]), 2)

    def test_disagreement_blocks(self):
        with self.assertRaises(ValueError):
            adjudicate(self.SHA, self.reviews(second="다른 문자"))

    def test_ocr_text_cannot_self_approve(self):
        with self.assertRaises(ValueError):
            adjudicate(self.SHA, [{"reviewer_id": "ocr-model", "transcription": "가나다"}])

    def test_same_identity_blocks(self):
        reviews = self.reviews()
        reviews[1]["reviewer_id"] = "human_one"
        with self.assertRaises(ValueError):
            adjudicate(self.SHA, reviews)

    def test_no_visual_attestation_blocks(self):
        reviews = self.reviews()
        reviews[1]["visual_review_attested"] = False
        with self.assertRaises(ValueError):
            adjudicate(self.SHA, reviews)

    def test_wrong_image_digest_blocks(self):
        reviews = self.reviews()
        reviews[0]["image_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            adjudicate(self.SHA, reviews)

    def test_build_real_manifest_only_on_verified_capture(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r1.png"
            Image.new("RGB", (140, 80), "white").save(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            case = {"case_id": "scan_01", "image": "r1.png", "sha256": digest,
                    "category": "korean", "capture_method": "camera_capture",
                    "verified_physical_capture": True, "permission_attested": True,
                    "license": "original owner permission"}
            case["reviews"] = self.reviews()
            for item in case["reviews"]:
                item["image_sha256"] = digest
            result = build_local_manifest({"cases": [case]}, root)
            self.assertEqual(result["cases"][0]["transcription_quality"], "human_checked_full")
            self.assertFalse(result["promotion_eligible"])
            case["verified_physical_capture"] = False
            with self.assertRaises(ValueError):
                build_local_manifest({"cases": [case]}, root)

    def test_no_permission_blocks(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "r1.png"
            Image.new("RGB", (140, 80), "white").save(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            case = {"case_id": "scan_01", "image": "r1.png", "sha256": digest,
                    "category": "korean", "capture_method": "camera_capture",
                    "verified_physical_capture": True, "permission_attested": False,
                    "license": "unknown", "reviews": self.reviews()}
            with self.assertRaises(ValueError):
                build_local_manifest({"cases": [case]}, root)


class C22SourceTests(unittest.TestCase):
    def test_pinned_revision_required(self):
        self.assertEqual(immutable_revision(SimpleNamespace(sha="a" * 40)), "a" * 40)
        with self.assertRaises(ValueError):
            immutable_revision(SimpleNamespace(sha="main"))

    def test_bad_image_rejected(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "fake.jpg"
            source.write_bytes(b"not an image")
            with self.assertRaises(ValueError):
                inspect_image(source)

    def test_consent_required(self):
        with patch.dict(os.environ, {"OCR_C22_EXTERNAL_DATA_CONSENT": "0"}):
            with self.assertRaises(RuntimeError):
                run_public(Path("/tmp/unused"), api_factory=lambda: object(),
                           download_factory=lambda **kwargs: None)

    def test_resolver_does_not_accept_other_subsets(self):
        class MissingApi:
            def list_repo_files(self, **kwargs):
                return ["AIHub/images/gist_3_1.jpg", "KAIST_Corrected/images/gist_4_3.jpg"]
        with self.assertRaises(ValueError):
            find_publisher_asset_paths(MissingApi(), "a" * 40)

    def test_safe_gist_archive_path_and_bounded_size(self):
        class TarApi:
            def list_repo_files(self, **kwargs):
                return ["GIST_Signboard/text_images.tar", "KAIST_Corrected/text_images.tar"]
            def list_repo_tree(self, **kwargs):
                return [SimpleNamespace(path="GIST_Signboard/text_images.tar", size=100000)]
        paths = find_publisher_asset_paths(TarApi(), "a" * 40)
        self.assertTrue(all(value == "archive:GIST_Signboard/text_images.tar" for value in paths.values()))
        self.assertEqual(archive_byte_budget(TarApi(), "a" * 40, "GIST_Signboard/text_images.tar"), 100000)

    def test_exact_selected_members_only(self):
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "crops.tar"
            with tarfile.open(archive, "w") as tar:
                for ident, preview, _ in GIST_CASES:
                    payload = b"sample-source-image-bytes" + ident.encode()
                    member = tarfile.TarInfo(name="text_images/0/" + ident + ".jpg")
                    member.size = len(payload)
                    tar.addfile(member, io.BytesIO(payload))
                ignored = tarfile.TarInfo(name="../../other_dataset/untrusted.txt")
                ignored.size = 4
                tar.addfile(ignored, io.BytesIO(b"junk"))
            extracted = extract_selected_crop_members(archive, Path(tmp))
            self.assertEqual(len(extracted), 3)
            self.assertFalse((Path(tmp).parent / "untrusted.txt").exists())

    def test_oversized_archive_blocks_score_but_not_receipt_intake(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "receipt.jpeg"
            image = Image.new("RGB", (360, 180), "white")
            draw = ImageDraw.Draw(image)
            for y in range(0, 180, 3):
                draw.line((0, y, 359, y), fill=(y % 255, 60, 90))
            image.save(source, quality=97)
            class Api:
                def dataset_info(self, repo):
                    return SimpleNamespace(sha="a" * 40)
                def list_repo_files(self, **kwargs):
                    return ["GIST_Signboard/text_images.tar"]
                def list_repo_tree(self, **kwargs):
                    return [SimpleNamespace(path="GIST_Signboard/text_images.tar", size=1427559424)]
            def download(**kwargs):
                self.assertEqual(kwargs["repo_id"], RECEIPT_REPO)
                return str(source)
            with patch.dict(os.environ, {"OCR_C22_EXTERNAL_DATA_CONSENT": "1"}):
                result = run_public(root / "out", api_factory=Api, download_factory=download)
            self.assertEqual(result["real_korean_scene_crops"]["status"], "BLOCKED_RESOURCE_BUDGET")
            self.assertIsNone(result["real_korean_scene_crops"]["aggregate"])
            self.assertEqual(len(result["korean_receipt_review_queue"]), 2)
            self.assertIsNone(result["real_korean_receipt_cer_wer"])

    def test_real_crops_score_only_published_labels(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "a.jpeg"
            im = Image.new("RGB", (360, 180), "white")
            draw = ImageDraw.Draw(im)
            for i in range(0, 180, 3):
                draw.line((0, i, 359, i), fill=(i % 255, 60, 90))
            im.save(source, quality=97)
            self.assertGreater(source.stat().st_size, 1024)
            def fake_download(**kwargs):
                self.assertIn(kwargs["repo_id"], (GIST_REPO, RECEIPT_REPO))
                self.assertEqual(kwargs["revision"], "a" * 40)
                return str(source)
            class FakeApi:
                def dataset_info(self, repo):
                    return SimpleNamespace(sha="a" * 40)
                def list_repo_files(self, **kwargs):
                    return ["GIST_Signboard/crops/0/" + item[0] + ".jpg" for item in GIST_CASES]
            texts = {k: expected for k, _, expected in GIST_CASES}
            def fake_ocr(path, psm):
                self.assertEqual(psm, 7)
                return "신영증권"
            with patch.dict(os.environ, {"OCR_C22_EXTERNAL_DATA_CONSENT": "1"}):
                result = run_public(root / "result", api_factory=FakeApi,
                                    download_factory=fake_download, ocr=fake_ocr)
            self.assertEqual(result["real_korean_scene_crops"]["aggregate"]["count"], 3)
            self.assertEqual(len(result["korean_receipt_review_queue"]), 2)
            self.assertIsNone(result["real_korean_receipt_cer_wer"])
            self.assertEqual(result["physically_verified_document_scans_with_two_human_reviews"], 0)
            self.assertFalse(result["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
