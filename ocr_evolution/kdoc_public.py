"""Small, independently sourced real Korean public-PDF smoke benchmark.

Corpus: ONTHEIT/KDoc-OCRBench-V2. These are *real public documents rasterized*
for OCR; do not claim physical scanner images or full-text gold truth.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter

import fitz

from .metrics import normalize


DATASET_ID = "ONTHEIT/KDoc-OCRBench-V2"
ANNOTATION_LICENSE = "CC-BY-4.0"
UNRESTRICTED = "이용허락범위 제한없음"


def load_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def exact_presence(text, observed):
    """Strict case/whitespace-normalized substring; unlike upstream fuzzy tests."""
    if not isinstance(text, str) or not text.strip():
        return False
    return " ".join(normalize(text).split()) in " ".join(normalize(observed).split())


def score_verified_text(prediction, tests):
    if not isinstance(tests, list):
        raise ValueError("tests must be a list")
    for item in tests:
        if item.get("type") != "present" or item.get("checked") != "verified":
            raise ValueError("only manually verified present-tests allowed")
    return {"checked": len(tests),
            "matched": sum(exact_presence(item["text"], prediction) for item in tests),
            "metric": "strict_verified_sentence_presence_not_CER_WER"}


def score_table_text(prediction, tests):
    """Cell text *presence*, NOT a table topology/layout metric."""
    if not isinstance(tests, list):
        raise ValueError("tests must be a list")
    for item in tests:
        if item.get("type") != "table" or item.get("checked") != "verified":
            raise ValueError("only verified table-cell tests allowed")
    return {"checked": len(tests),
            "matched": sum(exact_presence(item.get("cell", ""), prediction) for item in tests),
            "metric": "strict_cell_text_presence_not_table_structure"}


def _read_licenses(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        data = list(csv.DictReader(stream))
    return {row["filename"]: row for row in data}


def choose_docs(licenses, text_groups, table_groups, *, limit=2):
    """Deterministically choose unrestricted PDFs with both kinds of tests."""
    eligible = []
    for pdf, rights in sorted(licenses.items()):
        if (rights.get("license") != UNRESTRICTED or
            not rights.get("source_url", "").startswith("https://") or
            not pdf.endswith(".pdf") or pdf not in text_groups or
            pdf not in table_groups):
            continue
        # Avoid giant bulk-format files; just a reproducible non-random smoke subset.
        if pdf.startswith("(대량") or len(pdf) > 150:
            continue
        eligible.append(pdf)
    if len(eligible) < limit:
        raise ValueError("not enough eligible real public PDFs with verified text and table tests")
    return eligible[:limit]


def _group_tests(path, allowed_type):
    groups = defaultdict(list)
    for record in load_jsonl(path):
        if (record.get("type") == allowed_type and
            record.get("checked") == "verified" and
            record.get("page") == 1 and
            isinstance(record.get("pdf"), str)):
            groups[record["pdf"]].append(record)
    return groups


def evaluate_public(out_dir: Path, *, sample_count=2):
    """Explicit network opt-in; CI must not silently substitute synthetic data."""
    from huggingface_hub import HfApi, hf_hub_download
    if os.environ.get("OCR_REAL_DATA_NETWORK_CONSENT") != "1":
        raise RuntimeError("explicit OCR_REAL_DATA_NETWORK_CONSENT=1 required")
    if not 1 <= sample_count <= 5:
        raise ValueError("real page budget must be 1..5")
    info = HfApi().dataset_info(DATASET_ID)
    revision = info.sha
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("cannot pin immutable upstream revision")

    def get(path):
        return Path(hf_hub_download(repo_id=DATASET_ID, repo_type="dataset",
                                    filename=path, revision=revision))

    license_path = get("licenses.csv")
    text_path = get("text_present.jsonl")
    table_path = get("tables.jsonl")
    license_data = _read_licenses(license_path)
    texts = _group_tests(text_path, "present")
    tables = _group_tests(table_path, "table")
    chosen = choose_docs(license_data, texts, tables, limit=sample_count)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in chosen:
        pdf = get("pdfs/" + name)
        content = pdf.read_bytes()
        if not content.startswith(b"%PDF") or len(content) > 20 * 1024 * 1024:
            raise ValueError("PDF signature or byte budget invalid")
        with fitz.open(stream=content, filetype="pdf") as document:
            if document.page_count != 1 or document.is_encrypted:
                raise ValueError("single-page unencrypted public PDF required")
            page = document.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            if pix.width * pix.height > 20_000_000:
                raise ValueError("render pixel budget exceeded")
            # On disk only for local OCR input; not uploaded as an artifact.
            img = out_dir / "temporary-page.png"
            pix.save(str(img))
        start = perf_counter()
        try:
            process = subprocess.run(["tesseract", str(img), "stdout", "-l", "kor+eng",
                                      "--psm", "11"], capture_output=True, text=True,
                                     timeout=90, check=True)
        finally:
            img.unlink(missing_ok=True)
        observed = process.stdout.strip()
        rights = license_data[name]
        entries.append({
            "source_pdf": name, "license": rights["license"],
            "source_url": rights["source_url"], "attribution": rights.get("attribution", ""),
            "pdf_sha256": hashlib.sha256(content).hexdigest(),
            "ocr_text_sha256": hashlib.sha256(observed.encode("utf-8")).hexdigest(),
            "elapsed_ms": round((perf_counter() - start) * 1000),
            "text_presence": score_verified_text(observed, texts[name]),
            "table_cell_text_presence": score_table_text(observed, tables[name]),
            "structured_table_adjacency_f1": None,
            "table_structure_reason": "Tesseract plain text does not output row/column cell graph",
            "cer": None, "wer": None,
            "ground_truth_limit": "verified fragments; no full human-checked transcript",
            "capture_type": "rasterized_authentic_public_pdf_not_physical_scan",
        })
    report = {
        "schema_version": 1, "dataset": DATASET_ID,
        "dataset_revision": revision, "dataset_annotation_license": ANNOTATION_LICENSE,
        "source_count": len(entries), "real_public_pdf_pages": len(entries),
        "physical_scans_evaluated": 0,
        "image_origin": "real public-sector document pages rasterized by PyMuPDF",
        "selected_by": "sorted unrestricted licenses with verified text and table units; non-bulk",
        "sample_is_tiny": True,
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "cases": entries, "cer": None, "wer": None, "table_topology_accuracy": None,
        "independent_holdout": False, "promotion_eligible": False,
        "limitations": "No full gold transcription, no physical scans, no structured table parser. Exact substring recall is not the source benchmark official fuzzy score.",
    }
    (out_dir / "public-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = ["# C2.1 real-public-document smoke test", "",
            "Sources are real Korean public-sector PDFs, NOT physical scanner captures.",
            "Verified unit assertions are attributed to ONTHEIT (CC BY 4.0).", "",
            "| PDF (sha256 prefix) | Text present | Table cell text | CER/WER | Table structure |",
            "|---|---:|---:|---|---|"]
    for item in entries:
        t = item["text_presence"]; v = item["table_cell_text_presence"]
        rows.append(f'| {item["pdf_sha256"][:12]} | {t["matched"]}/{t["checked"]} | {v["matched"]}/{v["checked"]} | N/A | N/A |')
    rows.extend(["", "Human-reviewed full-text ground truth and table-grid predictions are unavailable.",
                 "No OCR model changes or automatic promotion.", ""])
    (out_dir / "public-results.md").write_text("\n".join(rows), encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=Path("reports/c21-public"))
    p.add_argument("--sample-count", type=int, default=2)
    args = p.parse_args()
    result = evaluate_public(args.output_dir, sample_count=args.sample_count)
    print(f'REAL PUBLIC PDF smoke complete: pages={result["real_public_pdf_pages"]} '
          f'physical_scans={result["physical_scans_evaluated"]} '
          "CER/WER=N/A table_topology=N/A")


if __name__ == "__main__":
    main()
