"""Local opt-in real-scan evaluation.

No network, no uploading images, no implicit data exfiltration. Full CER/WER
requires human-verified complete transcriptions; sparse snippets never fake it.
"""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

from PIL import Image

from .metrics import measure, _aggregate, normalize
from .table_structure import score_grid

KINDS = frozenset(("flatbed_scan", "camera_capture", "rasterized_public_pdf"))
CATEGORIES = frozenset(("korean", "table", "low_quality"))
SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]{1,160}$")


def _local_image(root, name):
    if not isinstance(name, str) or not SAFE_PATH.fullmatch(name):
        raise ValueError("unsafe image path")
    relative = Path(name)
    if relative.is_absolute() or any(p in ("..", "") for p in relative.parts):
        raise ValueError("unsafe image path")
    root = root.resolve(strict=True)
    image = (root / relative).resolve(strict=True)
    if not image.is_relative_to(root) or not image.is_file():
        raise ValueError("image escapes corpus")
    if image.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("image exceeds 20 MiB")
    with Image.open(image) as opened:
        if opened.format not in ("PNG", "JPEG", "TIFF"):
            raise ValueError("unsupported image")
        if opened.width * opened.height > 35_000_000:
            raise ValueError("image pixel budget exceeded")
        opened.verify()
    return image


def load_corpus(manifest_path: Path, root: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("public_split") != "development":
        raise ValueError("only explicit public development corpus is accepted")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("case count invalid")
    seen_cases, seen_hashes, cases_out = set(), set(), []
    for case in cases:
        ident, capture, category = case.get("case_id"), case.get("capture_method"), case.get("category")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9_]{2,60}", ident) or ident in seen_cases:
            raise ValueError("unsafe or duplicate case id")
        if capture not in KINDS or category not in CATEGORIES:
            raise ValueError("invalid document classification")
        provenance_kind = case.get("provenance_kind", "public_https")
        source = case.get("source_url")
        if provenance_kind == "public_https":
            parsed = urlparse(source if isinstance(source, str) else "")
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("public provenance HTTPS source required")
        elif provenance_kind == "user_owned_local":
            if case.get("permission_attested") is not True or source is not None:
                raise ValueError("private data needs local owner permission attestation, without URL")
        else:
            raise ValueError("unknown provenance kind")
        if not isinstance(case.get("license"), str) or not case["license"].strip():
            raise ValueError("document license must be explicitly documented")
        img = _local_image(root, case.get("image"))
        digest = sha256(img.read_bytes()).hexdigest()
        if digest != case.get("sha256") or digest in seen_hashes:
            raise ValueError("image digest mismatch or duplicate/leakage")
        transcript = case.get("transcription")
        if transcript is not None and (case.get("transcription_quality") != "human_checked_full" or
                                       not isinstance(transcript, str) or not transcript.strip()):
            raise ValueError("CER/WER requires audited full-page transcription")
        snippets = case.get("verified_snippets", [])
        if not isinstance(snippets, list) or any(not isinstance(x, str) or not x.strip() for x in snippets):
            raise ValueError("verified snippet list invalid")
        if transcript is None and not snippets and not case.get("expected_table"):
            raise ValueError("no verifiable annotation")
        if case.get("expected_table") is not None:
            score_grid(case["expected_table"], None)  # validate full grid
        seen_cases.add(ident)
        seen_hashes.add(digest)
        cases_out.append((case, img))
    return cases_out


def _presence(snippets, prediction):
    observed = " ".join(normalize(prediction).split())
    result = [(" ".join(normalize(item).split()) in observed) for item in snippets]
    return {"checked": len(result), "matched": sum(result),
            "recall": sum(result) / len(result) if result else None}


def evaluate_local_corpus(manifest_path: Path, corpus_root: Path,
                          tesseract="tesseract"):
    cases = load_corpus(manifest_path, corpus_root)
    per_category = defaultdict(list)
    details = []
    for case, img in cases:
        completed = subprocess.run(
            [tesseract, str(img), "stdout", "-l", "kor+eng", "--psm",
             "11" if case["category"] == "table" else "6"],
            capture_output=True, text=True, timeout=60, check=True)
        observed = completed.stdout.strip()
        metric = measure(case["transcription"], observed) if case.get("transcription") is not None else None
        if metric is not None:
            per_category[case["category"]].append(metric)
        details.append({
            "case_id": case["case_id"], "category": case["category"],
            "capture_method": case["capture_method"], "sha256": case["sha256"],
            "license": case["license"], "source_url": case.get("source_url"),
            "provenance_kind": case.get("provenance_kind", "public_https"),
            "cer": metric["char_errors"] / metric["reference_chars"] if metric else None,
            "wer": metric["word_errors"] / metric["reference_words"] if metric else None,
            "verified_snippet_recall": _presence(case.get("verified_snippets", []), observed),
            "table_structure": score_grid(case["expected_table"], None)
                 if case.get("expected_table") is not None else None,
            "transcription_kind": "human_checked_full" if metric else "sparse_verified_only",
            "predicted_structured_cells": False,
        })
    all_metrics = [m for group in per_category.values() for m in group]
    return {
        "schema_version": 1, "data_kind": "real_opt_in_scans",
        "source_count": len(cases),
        "full_transcriptions_count": len(all_metrics),
        "overall_cer_wer": _aggregate(all_metrics) if all_metrics else None,
        "category_cer_wer": {cat: _aggregate(group) for cat, group in per_category.items()},
        "cases": details,
        "promotion_eligible": False, "independent_hidden_holdout": False,
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run a local-only, audited real-scan OCR evaluation")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/c21-local/results.json"))
    args = parser.parse_args()
    result = evaluate_local_corpus(args.manifest, args.corpus_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Local real-scan evaluation complete: ",
          result["source_count"], "images;",
          result["full_transcriptions_count"], "human-verified full transcripts;")


if __name__ == "__main__":
    main()
