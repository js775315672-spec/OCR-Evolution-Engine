"""C2.2 independent real-photograph Korean OCR and receipt intake (development only).

Attributions:
K-STR-Bench (Han & Hong, ACCV 2026), GIST-Signboard subset, CC BY 4.0.
HumynLabs/Korean_Receipts_Dataset, CC BY 4.0.
No image files or OCR transcripts are uploaded to GitHub artifact storage.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image

from .metrics import measure, _aggregate

GIST_REPO = "hoonisone/K-STR-Bench"
RECEIPT_REPO = "HumynLabs/Korean_Receipts_Dataset"

# Published author-reviewed labels visible in the K-STR-Bench public data viewer.
# They are not separately re-transcribed by our reviewers. Domain = signboards.
GIST_CASES = (
    ("gist_3_1", "GIST_Signboard/text_images/0/gist_3_1.jpg", "신영증권"),
    ("gist_4_3", "GIST_Signboard/text_images/0/gist_4_3.jpg", "현대리바트"),
    ("gist_4_4", "GIST_Signboard/text_images/0/gist_4_4.jpg", "광주전시장"),
)
RECEIPT_FILES = (
    "Kgen_Korean Receipts_1005_1.JPEG",
    "Kgen_Korean Receipts_1005_2.JPEG",
)


def immutable_revision(info):
    rev = getattr(info, "sha", None)
    if not isinstance(rev, str) or len(rev) != 40 or any(ch not in "0123456789abcdef" for ch in rev):
        raise ValueError("dataset revision must be an immutable 40-digit SHA")
    return rev


def inspect_image(path: Path):
    if not path.is_file() or path.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("missing or oversized image")
    raw = path.read_bytes()
    if len(raw) < 1024:
        raise ValueError("image too small to trust")
    with Image.open(path) as img:
        if img.format not in ("JPEG", "PNG"):
            raise ValueError("unexpected source format")
        width, height = img.size
        if width * height > 25_000_000 or width < 20 or height < 20:
            raise ValueError("invalid pixel budget")
        img.verify()
    return {"image_sha256": sha256(raw).hexdigest(), "width": width,
            "height": height, "image_bytes": len(raw)}


def measure_published_crops(download, invoke_ocr):
    samples = []
    metrics = []
    for ident, remote_path, expected in GIST_CASES:
        image_path = download(GIST_REPO, remote_path)
        info = inspect_image(image_path)
        output = invoke_ocr(image_path, psm=7)
        stats = measure(expected, output)
        metrics.append(stats)
        samples.append({
            "case_id": ident, "upstream_path": remote_path, **info,
            "ground_truth_source": "publisher_reviewed_KSTR_GIST_label",
            "independent_second_review": False,
            "capture_type": "real_camera_scene_text_crop_not_paper_document",
            "category": "korean_scene_text",
            "cer": stats["char_errors"] / stats["reference_chars"],
            "wer": stats["word_errors"] / stats["reference_words"],
            "reference_chars": stats["reference_chars"],
            "char_errors": stats["char_errors"],
            "reference_words": stats["reference_words"],
            "word_errors": stats["word_errors"],
            "ocr_transcription_excluded_from_public_artifact": True,
        })
    return {"cases": samples, "aggregate": _aggregate(metrics),
            "metric_scope": "3 published-labelled real Korean signboard word crops, not full-page OCR",
            "promotion_eligible": False}


def intake_unlabeled_receipts(download):
    rows = []
    for index, filename in enumerate(RECEIPT_FILES, 1):
        image = download(RECEIPT_REPO, filename)
        info = inspect_image(image)
        rows.append({
            "case_id": f"korean_receipt_{index:02d}", "upstream_path": filename, **info,
            "license": "CC-BY-4.0", "source_dataset": RECEIPT_REPO,
            "photo_or_scan_status": "unverified_mixed_real_and_simulated_source",
            "human_verified_full_transcription": False,
            "second_review_signed": False,
            "cer": None, "wer": None, "promotion_eligible": False,
            "pending": "inspect physical source and obtain 2 independent full-text visual reviews",
        })
    return rows


def call_tesseract(path, *, psm):
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "kor+eng", "--psm", str(psm)],
        capture_output=True, text=True, check=True, timeout=45)
    return result.stdout.strip()


def find_publisher_asset_paths(api, revision):
    """Resolve published CSV image basenames to *actual* pinned repository paths.

    A preview path is not a promise that the underlying file is at that location.
    Never fetch another subset (AIHub/KAIST) by accident.
    """
    listed = api.list_repo_files(repo_id=GIST_REPO, repo_type="dataset", revision=revision)
    selected = {}
    for ident, preview_path, _ in GIST_CASES:
        basename = preview_path.rsplit("/", 1)[-1].lower()
        hits = [name for name in listed
                if name.startswith("GIST_Signboard/") and name.rsplit("/", 1)[-1].lower() == basename]
        if len(hits) != 1:
            sample = [name for name in listed if name.startswith("GIST_Signboard/")][:8]
            raise ValueError(f"cannot uniquely resolve {basename}; GIST repository examples: {sample}")
        selected[ident] = hits[0]
    return selected


def run_public(out_dir: Path, *, api_factory=None, download_factory=None, ocr=None):
    if os.environ.get("OCR_C22_EXTERNAL_DATA_CONSENT") != "1":
        raise RuntimeError("OCR_C22_EXTERNAL_DATA_CONSENT=1 required")
    if api_factory is None or download_factory is None:
        from huggingface_hub import HfApi, hf_hub_download
        api_factory = api_factory or HfApi
        download_factory = download_factory or hf_hub_download
    api = api_factory()
    revisions = {repo: immutable_revision(api.dataset_info(repo)) for repo in (GIST_REPO, RECEIPT_REPO)}
    asset_paths = find_publisher_asset_paths(api, revisions[GIST_REPO])
    by_preview = {path: asset_paths[ident] for ident, path, _ in GIST_CASES}
    def download(repo, relative):
        actual_path = by_preview[relative] if repo == GIST_REPO else relative
        return Path(download_factory(
            repo_id=repo, repo_type="dataset", filename=actual_path, revision=revisions[repo]))
    result = {
        "schema_version": 1, "phase": "C2.2",
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "external_dataset_revisions": revisions,
        "licenses": {GIST_REPO: "GIST-Signboard subset CC-BY-4.0 only",
                     RECEIPT_REPO: "CC-BY-4.0"},
        "attributions": {
            GIST_REPO: "Han, Myounghun and Hong, Jin-Hyuk, K-STR-Bench, ACCV 2026",
            RECEIPT_REPO: "HumynLabs Korean Receipts Dataset",
        },
        "reference_integrity": "published author-reviewed scene-text labels; no second blind review",
        "image_artifact_policy": "no raw source images or unredacted OCR text in artifacts",
        "real_korean_scene_crops": measure_published_crops(download, ocr or call_tesseract),
        "korean_receipt_review_queue": intake_unlabeled_receipts(download),
        "physically_verified_document_scans_with_two_human_reviews": 0,
        "real_korean_receipt_cer_wer": None,
        "independent_hidden_holdout": False,
        "promotion_eligible": False,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    aggregate = result["real_korean_scene_crops"]["aggregate"]
    lines = ["# C2.2 real Korean camera-source intake", "",
             "Scene-text crop CER/WER use K-STR-Bench publisher labels; NOT a paper document score.",
             "Korean receipt images have NO independently reviewed transcript (CER/WER=N/A).", "",
             "| Source | Cases | CER | WER |",
             "|---|---:|---:|---:|",
             f'| Korean real signboard photo crops | {aggregate["count"]} | {aggregate["cer"]:.4f} | {aggregate["wer"]:.4f} |',
             f'| Korean mixed-source receipt images (unlabeled) | {len(result["korean_receipt_review_queue"])} | N/A | N/A |',
             "", "All exact source SHA-256 and upstream revisions are in results.json.",
             "No physical receipt image has been certified by a reviewer. No automatic improvement claim.", ""]
    (out_dir / "results.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("reports/c22-public"))
    args = parser.parse_args()
    report = run_public(args.output_dir)
    metrics = report["real_korean_scene_crops"]["aggregate"]
    print("REAL KOREAN SCENE TEXT: n=", metrics["count"],
          "CER=", round(metrics["cer"], 5), "WER=", round(metrics["wer"], 5),
          "; UNVERIFIED RECEIPTS:", len(report["korean_receipt_review_queue"]),
          "; VERIFIED SCANS: 0")


if __name__ == "__main__":
    main()
