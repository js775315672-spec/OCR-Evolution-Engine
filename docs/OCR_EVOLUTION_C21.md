# C2.1 — Real-source Korean OCR evaluation and table structure

**Development evidence only.** All work stays inside this OCR repository's
existing Draft PR #2; never merge, update main or connect to the Ouroboros,
Cerberus, Fenrir repositories, ledgers, credentials or schedules.

## 1. What is actually evaluated?

### A. Real Korean public-sector PDFs (CI, network opt-in)

The upstream corpus is
[ONTHEIT/KDoc-OCRBench-V2](https://huggingface.co/datasets/ONTHEIT/KDoc-OCRBench-V2).
It has 849 Korean government PDF pages with human-reviewed **unit checks**:
sentence-presence tests and table-cell/neighbor tests. The dataset annotations
are CC BY 4.0 (attribute ONTHEIT). The original PDFs carry per-file rights,
either `이용허락범위 제한없음` or KOGL Type 1; the smoke selection **only**
allows unrestricted PDFs with verified tests and HTTPS original source URLs.
The upstream revision SHA is captured before fetching and then pinned for
all downloads. Two matching non-bulk pages are chosen in lexicographic order;
selected PDF SHA-256, rights, source URL, original attribution, runner and
revision SHA are emitted in the report.

These are **genuine Korean documents rasterized for OCR**, **NOT confirmed
physical scans or photographed paper**. PDFs/derived bitmap images are read
inside CI and are NOT uploaded as artifacts. No user uploads are sent.

Measurements on these documents:

- Strict NFC + whitespace normalized sentence-exact-presence checks (verified
  fragments only); this is **stricter than** the upstream fuzzy benchmark.
- Strict table-cell text presence, **not** table layout accuracy.
- Four-directional verified table neighbor accuracy using actual Tesseract TSV
  word/line bounding boxes. Ambiguous duplicate text and missing detections
  count as failures. This is a deliberately simple **geometric proxy**,
  **not** ground-truth table-grid F1 or TEDS.
- **CER/WER = N/A** on this dataset, as it has manually verified unit assertions
  but not page-wide fully audited transcriptions.

A failure to download or verify source data is a **failed/blocked CI job**;
never substitute synthetic data and report it as real.

### B. Real physical scan/camera image with audited full text (local only)

`ocr_evolution.real_corpus` accepts an explicit UTF-8 manifest that points to
locally held PNG/JPEG/TIFF images. Every image is content-hashed, restricted to
the selected corpus folder, size-checked and source-licensed. Mark each image
as `flatbed_scan`, `camera_capture`, or `rasterized_public_pdf`.
Set `category` to `korean`, `table`, or `low_quality` **only after
visually reviewing it**; the term low_quality is not inferred just because
OCR failed.

Each manually reviewed full-page transcription must set
`transcription_quality: human_checked_full`. Only those cases contribute
exact Unicode-NFC CER/WER, micro-aggregated by reference character/word counts.
When only verified snippets are available, the program reports snippet recall
and explicitly returns `null` for CER/WER. This blocks invented ground truth.

Example manifest (fill in real image path and actual SHA-256; do not commit
the images or personal documents):

```json
{
  "schema_version": 1,
  "public_split": "development",
  "cases": [{
    "case_id": "scan_001",
    "image": "scan_001.png",
    "sha256": "<64-char SHA-256 of uploaded real image>",
    "category": "korean",
    "capture_method": "flatbed_scan",
    "provenance_kind": "user_owned_local",
    "permission_attested": true,
    "license": "evaluation permitted by owner",
    "transcription": "사람이 실제 이미지에서 확인한 전체 원문",
    "transcription_quality": "human_checked_full",
    "verified_snippets": ["사람이 실제"]
  }]
}
```

Run (requires Tesseract `kor+eng`, Python `.[test]` dependencies):

```sh
python -m ocr_evolution.real_corpus \
  --manifest /private/ocr/manifest.json \
  --corpus-root /private/ocr \
  --output /private/ocr-results/results.json
```

The tool has no HTTP client, no upload or model-training side effects, and
rejects missing/duplicated or tampered files. Local files are never committed.
For private scans, use `provenance_kind: user_owned_local` and
`permission_attested: true` with no source URL. For public scans, use
`provenance_kind: public_https` and a genuine HTTPS origin URL. Neither
path transmits the image off-device.

### C. Exact table-grid metric

`score_grid(expected_rows, predicted_rows)` reports micro-style precision,
recall and F1 for **positioned cell values**, and separately the F1 for exact
`right`/`down` adjacency edges. Row and column positions and adjacent
strings must agree; swapped columns fail. An engine that outputs only flat OCR
text supplies `predicted=None` and receives **not measurable**, not a
fabricated 0% or 100%. Ragged/merged cells require a future span-aware schema.

## 2. Required CI gates

- Windows and Linux: all security, source-rights, source-integrity, table-cell,
  adjacency and CER/WER tests.
- Linux: execute real Tesseract on the public two-page deterministic sample,
  archive `reports/c21-real-public/public-results.json` and `.md` with
  upstream revision+file SHA/provenance and honest N/A fields.
- C1 + C2 CI must remain green at exactly the latest head commit.
- Do not label public benchmark data as hidden holdout or model improvement.

## 3. Remaining work

1. Acquire/permission-check **actual paper scans or camera captures** and
   human-verified full-page Korean transcriptions for CER/WER.
2. Add genuinely audited low-quality subsets with blur/skew/resolution metadata.
3. Connect a table parser that emits row/column grids and supports rowspan and
   colspan, then measure exact grid and TEDS on independently reviewed tables.
4. Establish source-group-leakage-free holdouts, blinded test reviewers, run
   costs/time and a nontrivial sample size before any C3 autonomous improvement.

The current code makes those measurements possible but **does not claim**
real-scan coverage, human-verified full-text OCR scores on the public corpus,
full table structural accuracy or sustained AI self-improvement.
