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
import tarfile

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
        if img.format not in ("JPEG", "PNG", "MPO", "WEBP", "TIFF", "BMP"):
            raise ValueError(f"unexpected source format: {img.format!r}")
        width, height = img.size
        if width * height > 25_000_000 or width < 20 or height < 20:
            raise ValueError("invalid pixel budget")
        img.verify()
    return {"image_sha256": sha256(raw).hexdigest(), "width": width,
            "height": height, "image_bytes": len(raw), "decoded_format": img.format}


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
    """Resolve individual GIST crops or the official text_images.tar archive.

    Upstream distributes text crops in a tar, not as individual HF files.
    Refuse any KAIST/AIHub substitution and any ambiguous basename.
    """
    listed = api.list_repo_files(repo_id=GIST_REPO, repo_type="dataset", revision=revision)
    paths = {}
    complete = True
    for ident, preview, _ in GIST_CASES:
        name = preview.rsplit("/", 1)[-1].lower()
        hits = [p for p in listed if p.startswith("GIST_Signboard/")
                and p.rsplit("/", 1)[-1].lower() == name]
        if len(hits) != 1:
            complete = False
            break
        paths[ident] = hits[0]
    if complete:
        return paths
    tar_candidates = [p for p in listed if p == "GIST_Signboard/text_images.tar"]
    if len(tar_candidates) == 1:
        return {ident: "archive:" + tar_candidates[0] for ident, _, _ in GIST_CASES}
    sample = [p for p in listed if p.startswith("GIST_Signboard/")][:10]
    raise ValueError(f"no authorized GIST crop files or archive; available: {sample}")


def archive_byte_budget(api, revision, archive_path):
    """Require verified remote archive metadata before any large transfer."""
    tree = api.list_repo_tree(repo_id=GIST_REPO, repo_type="dataset",
                              revision=revision, path_in_repo="GIST_Signboard",
                              recursive=False, expand=True)
    for entry in tree:
        if getattr(entry, "path", None) == archive_path:
            size = getattr(entry, "size", None)
            if not isinstance(size, int) or size <= 0 or size > 750 * 1024 * 1024:
                raise ValueError(f"GIST text crop archive exceeds 750 MiB budget or size unknown: {size}")
            return size
    raise ValueError("pinned GIST archive size metadata not found")


def extract_selected_crop_members(archive_path, scratch_dir):
    """Read individual safe tar members without extracting arbitrary paths."""
    selected = {}
    with tarfile.open(archive_path, "r:*") as tar:
        members = {}
        wanted = {p.rsplit("/", 1)[-1].lower(): ident for ident, p, _ in GIST_CASES}
        for member in tar:
            base = member.name.rsplit("/", 1)[-1].lower()
            if base not in wanted:
                continue
            if not member.isfile() or member.size <= 0 or member.size > 12 * 1024 * 1024:
                raise ValueError("bad source crop tar member")
            ident = wanted[base]
            if ident in members:
                raise ValueError("duplicate ambiguous source crop inside tar")
            fileobj = tar.extractfile(member)
            if fileobj is None:
                raise ValueError("unreadable tar entry")
            payload = fileobj.read(12 * 1024 * 1024 + 1)
            if len(payload) != member.size:
                raise ValueError("invalid crop member length")
            path = Path(scratch_dir) / (ident + ".jpg")
            path.write_bytes(payload)
            members[ident] = path
        if len(members) != len(GIST_CASES):
            raise ValueError(f"source crop IDs missing from tar: {sorted(set(wanted.values()) - set(members))}")
        return members


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
    with TemporaryDirectory(prefix="ocr-c22-sourced-") as scratch:
        extracted = {}
        def download(repo, relative):
            actual_path = by_preview[relative] if repo == GIST_REPO else relative
            if repo == GIST_REPO and actual_path.startswith("archive:"):
                if not extracted:
                    tar_path = actual_path[len("archive:"):]
                    archive_byte_budget(api, revisions[repo], tar_path)
                    local_archive = download_factory(
                        repo_id=repo, repo_type="dataset", filename=tar_path, revision=revisions[repo])
                    extracted.update(extract_selected_crop_members(local_archive, scratch))
                ident = next(key for key, original, _ in GIST_CASES if original == relative)
                return extracted[ident]
            return Path(download_factory(
                repo_id=repo, repo_type="dataset", filename=actual_path, revision=revisions[repo]))
        try:
            gist = measure_published_crops(download, ocr or call_tesseract)
        except ValueError as exc:
            if "exceeds 750 MiB budget" not in str(exc):
                raise
            gist = {
                "status": "BLOCKED_RESOURCE_BUDGET",
                "cases": [], "aggregate": None, "measured_count": 0,
                "reason": str(exc),
                "metric_scope": "publisher-reviewed real Korean scene crops unavailable within bounded transfer",
                "promotion_eligible": False,
            }
        # Korean receipt acquisition is independent of the optional signboard crop benchmark.
        receipts = intake_unlabeled_receipts(download)
    result = {
        "schema_version": 1, "phase": "C2.2",
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "external_dataset_revisions": revisions,
        "source_package_mode": ("pinned_text_images_tar" if
                                any(p.startswith("archive:") for p in asset_paths.values())
                                else "individually_pinned_files"),
        "licenses": {GIST_REPO: "GIST-Signboard subset CC-BY-4.0 only",
                     RECEIPT_REPO: "CC-BY-4.0"},
        "attributions": {
            GIST_REPO: "Han, Myounghun and Hong, Jin-Hyuk, K-STR-Bench, ACCV 2026",
            RECEIPT_REPO: "HumynLabs Korean Receipts Dataset",
        },
        "reference_integrity": "published author-reviewed scene-text labels; no second blind review",
        "image_artifact_policy": "no raw source images or unredacted OCR text in artifacts",
        "real_korean_scene_crops": gist,
        "korean_receipt_review_queue": receipts,
        "physically_verified_document_scans_with_two_human_reviews": 0,
        "real_korean_receipt_cer_wer": None,
        "independent_hidden_holdout": False,
        "promotion_eligible": False,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    aggregate = result["real_korean_scene_crops"]["aggregate"]
    scene_row = (f'| Korean real signboard photo crops | {aggregate["count"]} | '
                 f'{aggregate["cer"]:.4f} | {aggregate["wer"]:.4f} |') if aggregate else (
                 '| Korean real signboard photo crops (transfer budget BLOCKED) | 0 | N/A | N/A |')
    lines = ["# C2.2 real Korean camera-source intake", "",
             "Scene-text crop CER/WER use K-STR-Bench publisher labels; NOT a paper document score.",
             "Korean receipt images have NO independently reviewed transcript (CER/WER=N/A).", "",
             "| Source | Cases | CER | WER |",
             "|---|---:|---:|---:|",
             scene_row,
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
    if metrics is None:
        print("REAL KOREAN SCENE TEXT BLOCKED: budget; CER/WER=N/A")
    else:
        print("REAL KOREAN SCENE TEXT: n=", metrics["count"],
              "CER=", round(metrics["cer"], 5), "WER=", round(metrics["wer"], 5))
    print("UNVERIFIED RECEIPT IMAGES:", len(report["korean_receipt_review_queue"]),
          "; PHYSICAL SCANS WITH TWO HUMAN TRANSCRIPTIONS: 0")


if __name__ == "__main__":
    main()
