"""C2.2.1: strictly local 2-10 physical-paper photo/scan OCR audit.

No OCR/model transcript becomes ground truth. All evidence and reviews must be
supplied by real, independent people; a program cannot prove that by itself.
Never use this as a hidden holdout or automatically promote a model.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime

from .c22_review import adjudicate
from .metrics import measure, _aggregate, normalize
from .real_corpus import _local_image

_ID = re.compile(r"^[a-z][a-z0-9_]{2,60}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_CATEGORIES = frozenset(("korean", "table", "low_quality"))
_CAPTURES = frozenset(("camera_capture", "flatbed_scan"))
_REVIEW_FILE_LIMIT = 80 * 1024


def _restricted_file(root: Path, filename: str, max_size: int) -> Path:
    if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,160}", filename):
        raise ValueError("unsafe relative evidence file name")
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("evidence path traversal")
    resolved_root = root.resolve(strict=True)
    target = (resolved_root / relative).resolve(strict=True)
    if not target.is_relative_to(resolved_root) or not target.is_file():
        raise ValueError("evidence outside selected private corpus")
    if target.stat().st_size > max_size:
        raise ValueError("evidence exceeds size budget")
    return target


def _recorded_time(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("review time missing")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("review time invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("review timestamp needs explicit timezone")


def _load_review(root: Path, file: str, expected_case: str, image_digest: str) -> dict:
    path = _restricted_file(root, file, _REVIEW_FILE_LIMIT)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("case_id") != expected_case:
        raise ValueError("review not bound to the exact case")
    if data.get("image_sha256") != image_digest:
        raise ValueError("review image digest mismatch")
    if data.get("visual_review_attested") is not True or data.get("blind_review_attested") is not True:
        raise ValueError("visual and blinded human review attestations required")
    if data.get("no_ocr_assistance_attested") is not True:
        raise ValueError("OCR-derived review cannot serve as human ground truth")
    _recorded_time(data.get("reviewed_at"))
    return data


def validate_batch(request: dict, root: Path):
    """Return approved in-memory cases; fail the *entire* batch on uncertainty."""
    if not isinstance(request, dict) or request.get("schema_version") != 1:
        raise ValueError("unsupported private batch schema")
    if request.get("data_split") != "development":
        raise ValueError("review corpus must not claim independent hidden holdout")
    cases = request.get("cases")
    if not isinstance(cases, list) or not 2 <= len(cases) <= 10:
        raise ValueError("exactly 2 to 10 physical captures required")
    seen_ids, seen_digests, validated = set(), set(), []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        ident = case.get("case_id")
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in seen_ids:
            raise ValueError("invalid or duplicate case ID")
        category, capture = case.get("category"), case.get("capture_method")
        if category not in _CATEGORIES or capture not in _CAPTURES:
            raise ValueError("unknown case category or physical capture method")
        if case.get("verified_physical_capture") is not True:
            raise ValueError("physical paper photo/scan provenance not reviewed")
        if case.get("permission_attested") is not True:
            raise ValueError("owner/reuse permission missing")
        if case.get("human_original_document_attested") is not True:
            raise ValueError("cannot classify simulated PDF/rendering as physical capture")
        if not isinstance(case.get("license"), str) or not case["license"].strip():
            raise ValueError("rights basis required")
        group = case.get("source_group")
        if not isinstance(group, str) or not _ID.fullmatch(group):
            raise ValueError("source group is required for leakage auditing")
        if category == "low_quality" and not isinstance(case.get("quality_defect"), str):
            raise ValueError("explicit low-quality evidence required")
        image = _local_image(root, case.get("image"))
        digest = sha256(image.read_bytes()).hexdigest()
        if digest != case.get("sha256") or not _SHA.fullmatch(digest) or digest in seen_digests:
            raise ValueError("image checksum mismatch or duplicate")
        review_files = case.get("review_files")
        if not isinstance(review_files, list) or len(review_files) != 2 or review_files[0] == review_files[1]:
            raise ValueError("two separately submitted review files required")
        reviews = [_load_review(root, name, ident, digest) for name in review_files]
        reviewed = adjudicate(digest, reviews)
        # The two identities are claimed, not cryptographically authenticated.
        validated.append({"case_id": ident, "image_path": image, "sha256": digest,
                          "category": category, "capture_method": capture,
                          "source_group": group, "reference": reviewed["text"],
                          "reference_sha256": reviewed["reference_sha256"],
                          "review_status": reviewed["review_status"]})
        seen_ids.add(ident)
        seen_digests.add(digest)
    if len({item["source_group"] for item in validated}) < 2:
        raise ValueError("at least two separate document source groups required")
    return validated


def _run_tesseract(image: Path, category: str, binary="tesseract") -> str:
    result = subprocess.run(
        [binary, str(image), "stdout", "-l", "kor+eng", "--psm",
         "11" if category == "table" else "6"],
        capture_output=True, text=True, check=True, timeout=60)
    return result.stdout.strip()


def evaluate_private_batch(request: dict, root: Path, *, ocr=None) -> dict:
    approved = validate_batch(request, root)  # no OCR runs before full approval
    evaluator = ocr if ocr is not None else _run_tesseract
    results, by_category = [], defaultdict(list)
    for item in approved:
        output = evaluator(item["image_path"], item["category"])
        stats = measure(item["reference"], output)
        by_category[item["category"]].append(stats)
        results.append({
            "case_id": item["case_id"], "image_sha256": item["sha256"],
            "reference_sha256": item["reference_sha256"],
            "category": item["category"], "capture_method": item["capture_method"],
            "source_group_digest": sha256(item["source_group"].encode()).hexdigest(),
            "cer": stats["char_errors"] / stats["reference_chars"],
            "wer": stats["word_errors"] / stats["reference_words"],
            "char_errors": stats["char_errors"],
            "reference_chars": stats["reference_chars"],
            "word_errors": stats["word_errors"],
            "reference_words": stats["reference_words"],
            "ground_truth": item["review_status"],
        })
    aggregate = _aggregate([metric for values in by_category.values() for metric in values])
    return {
        "schema_version": 1, "phase": "C2.2.1",
        "status": "MEASURED_WITH_TWO_CLAIMED_HUMAN_REVIEWS",
        "actual_captured_cases": len(approved),
        "source_groups": len({item["source_group"] for item in approved}),
        "overall": aggregate,
        "by_category": {cat: _aggregate(rows) for cat, rows in sorted(by_category.items())},
        "cases": results, "private_images_uploaded": False,
        "full_ground_truth_exported": False,
        "human_identity_verified_cryptographically": False,
        "independent_hidden_holdout": False,
        "promotion_eligible": False,
        "limitations": "Reviewer claims and physical provenance require independent human confirmation; development-only results are not evidence of generalization.",
    }


def _private_output_path(path: Path) -> None:
    """Prevent writing even redacted output into a checkout/repository."""
    target = path.resolve()
    for parent in (target.parent, *target.parent.parents):
        if (parent / ".git").exists():
            raise ValueError("private evaluation reports must be outside any Git checkout")


def write_private_report(path: Path, result: dict) -> None:
    _private_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    path.chmod(0o600)


def ci_gate_status() -> dict:
    """CI cannot manufacture private photos, reviewer identities or full transcripts."""
    return {
        "phase": "C2.2.1",
        "contract_tests": "run_separately",
        "real_physical_scans_with_confirmed_two_human_reviews": 0,
        "real_korean_scan_cer": None, "real_korean_scan_wer": None,
        "evaluation_gate": "BLOCKED_MISSING_INDEPENDENT_HUMAN_REVIEW_EVIDENCE",
        "promotion_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline-only 2-10 human-reviewed scan audit")
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--private-output", type=Path)
    parser.add_argument("--ci-status", action="store_true")
    args = parser.parse_args()
    if args.ci_status:
        print(json.dumps(ci_gate_status(), sort_keys=True))
        return
    if not (args.batch and args.root and args.private_output):
        parser.error("--batch, --root and --private-output are required")
    request = json.loads(args.batch.read_text(encoding="utf-8"))
    result = evaluate_private_batch(request, args.root)
    write_private_report(args.private_output, result)
    print("LOCAL OCR MEASURED: cases =", result["actual_captured_cases"],
          "CER =", round(result["overall"]["cer"], 6),
          "WER =", round(result["overall"]["wer"], 6))
    print("Local report written; no source images, OCR text or transcriptions uploaded.")


if __name__ == "__main__":
    main()
