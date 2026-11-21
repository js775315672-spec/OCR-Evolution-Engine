"""Reproducible, labeled *synthetic development* images and real Tesseract OCR.

This deliberately cannot approve model improvement: the public fixtures are
not a hidden holdout. The runner only reads images it generated in out_dir.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .metrics import CATEGORIES, evaluate_predictions

_ID = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def load_manifest(path: Path) -> tuple[dict, bytes]:
    source = path.read_bytes()
    manifest = json.loads(source)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    if manifest.get("source") != "original_synthetic_fixtures":
        raise ValueError("unverified fixture provenance")
    if manifest.get("split") != "development":
        raise ValueError("public fixtures cannot be holdout")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("invalid case count")
    ids = set()
    categories = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("invalid case")
        ident = case.get("case_id")
        text = case.get("expected_text")
        category = case.get("category")
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in ids:
            raise ValueError("unsafe or duplicate case id")
        if category not in CATEGORIES:
            raise ValueError("invalid fixture category")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("missing or excessive reference")
        if category == "table" and any(len(line.split("\t")) != 3 for line in text.splitlines()):
            raise ValueError("table reference must have three tab-separated columns")
        ids.add(ident)
        categories.add(category)
    if categories != CATEGORIES:
        raise ValueError("all three fixture categories required")
    return manifest, source


def render(case: dict, out_file: Path, font_path: str) -> str:
    """Draw a clean Korean/table page or degrade it into a low quality scan."""
    font = ImageFont.truetype(font_path, 42)
    image = Image.new("RGB", (1180, 500), "white")
    draw = ImageDraw.Draw(image)
    category = case["category"]
    if category == "table":
        rows = [line.split("\t") for line in case["expected_text"].splitlines()]
        widths = (420, 300, 370)
        left, top, row_height = 40, 55, 100
        for row_index, cells in enumerate(rows):
            x = left
            y = top + row_index * row_height
            for col_index, cell in enumerate(cells):
                width = widths[col_index]
                draw.rectangle((x, y, x+width, y+row_height), outline="#353535", width=2)
                draw.text((x+20, y+25), cell, fill="black", font=font)
                x += width
    else:
        draw.multiline_text((55, 95), case["expected_text"], fill="black",
                            font=font, spacing=34)
    if category == "low_quality":
        image = image.resize((590, 250), Image.Resampling.BILINEAR)
        image = ImageEnhance.Contrast(image).enhance(0.65)
        image = image.filter(ImageFilter.GaussianBlur(0.85))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_file, format="PNG")
    return hashlib.sha256(out_file.read_bytes()).hexdigest()


def _run(args: list[str]) -> str:
    finished = subprocess.run(args, capture_output=True, text=True, check=True, timeout=45)
    return finished.stdout


def segmentation_mode(category: str) -> int:
    """Use sparse-text mode for grids; keep prose in uniform-block mode."""
    if category not in CATEGORIES:
        raise ValueError("unsupported OCR fixture category")
    return 11 if category == "table" else 6


def benchmark(manifest_path: Path, output_dir: Path, font_path: str,
              tesseract: str = "tesseract") -> dict:
    manifest, manifest_bytes = load_manifest(manifest_path)
    if not Path(font_path).is_file():
        raise FileNotFoundError("explicit Unicode font missing")
    version_process = subprocess.run([tesseract, "--version"], capture_output=True,
                                     text=True, check=True, timeout=15)
    engine_version = (version_process.stdout or version_process.stderr).strip()
    languages = _run([tesseract, "--list-langs"])
    if "kor" not in languages.split() or "eng" not in languages.split():
        raise RuntimeError("kor and eng traineddata are required")
    images = output_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    predictions = []
    for case in manifest["cases"]:
        image = images / (case["case_id"] + ".png")
        image_sha = render(case, image, font_path)
        psm = segmentation_mode(case["category"])
        output = _run([tesseract, str(image), "stdout", "-l", "kor+eng", "--psm", str(psm)])
        predictions.append({
            **case, "split": "development", "observed_text": output.strip(),
            "page_segmentation_mode": psm,
            "image_file": "images/" + image.name, "image_sha256": image_sha,
        })
    measurements = evaluate_predictions(predictions)
    report = {
        "schema_version": 1,
        "source": "original_synthetic_fixtures",
        "license": manifest["license"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "git_sha": os.getenv("GITHUB_SHA", "unrecorded-local"),
        "run_id": os.getenv("GITHUB_RUN_ID", "unrecorded-local"),
        "tesseract_version": engine_version.strip() or "see runner logs",
        "font_path": str(Path(font_path).name),
        "measurements": measurements,
        "predictions": predictions,
        "limits": "Synthetic, public, development-only fixtures. No external generalization or autonomous improvement claim.",
    }
    (output_dir / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    lines = ["# C2 synthetic OCR measurement", "",
             "**NOT an independent holdout or evidence of generalization.**", "",
             "| Category | Cases | CER | WER |",
             "|---|---:|---:|---:|"]
    for category, data in measurements["by_category"].items():
        lines.append(f'| {category} | {data["count"]} | {data["cer"]:.4f} | {data["wer"]:.4f} |')
    total = measurements["overall"]
    lines.append(f'| **TOTAL** | **{total["count"]}** | **{total["cer"]:.4f}** | **{total["wer"]:.4f}** |')
    lines.extend(["", "The original images, recognized strings and manifest hashes are in the artifact.",
                  "Whitespace is preserved for CER, and split into tokens for WER.",
                  "Rates are exact edit distances divided by reference lengths; insertions can exceed 100%.",
                  "No automatic candidate promotion is permitted.", ""])
    (output_dir / "results.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/c2_synthetic_manifest.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/c2"))
    parser.add_argument("--font", required=True, help="Path to a Unicode font supporting Korean")
    parser.add_argument("--tesseract", default="tesseract")
    args = parser.parse_args()
    report = benchmark(args.manifest, args.out_dir, args.font, args.tesseract)
    overall = report["measurements"]["overall"]
    print(f'Synthetic DEV only: n={overall["count"]} CER={overall["cer"]:.4f} WER={overall["wer"]:.4f}')


if __name__ == "__main__":
    main()
