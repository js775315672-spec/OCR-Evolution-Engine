# OCR Evolution Engine C2.2.1 — private 2–10 real physical scan OCR protocol

**Status: software/CI work in progress; real two-human source evidence NOT supplied.**

This phase extends existing Draft PR #2 on `feat/ocr-evolution-c1` (base
`feat/ocr-mvp`); `main` unchanged, no merge or automatic deployment.
Ouroboros, Cerberus and Fenrir data, ledgers, credentials, agents, and model
outputs must never appear in this evaluation. These scripts perform NO HTTP
requests and upload NO images or text.

## Verified scope vs blocked scope

The two earlier publicly downloaded HumynLabs receipt images **cannot** be
counted as 2 genuine paper scans: that collection mixes real and simulated
receipts, each image's acquisition provenance is unverified, and full-page
human ground truth does not exist. The public KDoc PDF pages are authentic
government documents rendered from PDFs, not verified physical paper scans.

A Python unit test with pretend reviewers or drawn images establishes only
that a validator handles inputs correctly. It does **not** constitute a real
review, a real scan, independent human verification or a measured OCR result.

Only actual documents captured from **real paper** by a camera or flatbed
scanner, with documented reuse permission and *two independently typed full
transcriptions*, qualify for this phase. The program cannot prove the human
identity or that either person really examined the original; those are
explicit operator attestations requiring outside human supervision.

### Optional browser review interface (offline)

Open [tools/c221_offline_reviewer.html](../tools/c221_offline_reviewer.html)
from the local repository in a browser, without internet. Each real reviewer
opens the image and types the entire transcription, independently. The tool
uses browser SHA-256 to bind the selected image bytes to the exported JSON
and refuses to export unless each reviewer personally checks visual, blind
and no-OCR-assistance attestations. It has no network APIs or external assets;
a CSP blocks network connections. One reviewer exports
`reviewer_a_01.json`, the other `reviewer_b_01.json`. Keep these files
outside Git, put them in `reviews/` in the private root, and verify each
file's reviewer identity and original image hash before running the CLI.

The browser interface does **not** verify real identities and does **not**
create independent second reviewer automatically. Browser support for image
preview and `crypto.subtle` varies; use a compatible local browser or
fill the JSON directly from the private templates.

## Evidence-backed receipt candidate intake (2 actual downloaded files, NOT verified paper)

A prior real GitHub Actions run [44958514838](https://github.com/js775315672-spec/OCR-Evolution-Engine/actions/runs/44958514838)
actually downloaded two source images and recorded immutable upstream revision,
per-image SHA-256, dimensions and decoded formats. Those facts are pinned in
[`benchmarks/c221_real_receipt_review_queue.json`](../benchmarks/c221_real_receipt_review_queue.json).
Both candidates are **MPO encoded images** and belong to a public collection
containing both physically collected and simulated receipts. Thus the file
hashes are trustworthy as byte identity, but **physical real-paper origin
is NOT VERIFIED**. No independent full text transcription is present.

To obtain those exact source files *privately* for genuine external inspection:

```sh
python -m pip install -e ".[test]"
python -m pip install "huggingface_hub>=0.34,<2"
# Explicit owner/operator network download consent required:
OCR_C221_EXTERNAL_DATA_CONSENT=1 python -m ocr_evolution.c221_source_intake \
  --queue benchmarks/c221_real_receipt_review_queue.json \
  --private-dir /private/c221-original-public-candidates
```

The source downloader pins the upstream dataset commit, checks **every**
byte-hash, recorded size, decoded image format and dimensions against actual
GitHub CI evidence, refuses to overwrite existing folders, and **never**
writes a copy inside Git. It creates only a local `REVIEW_STATUS.json`
with real-world photo provenance and two-human transcriptions **both marked
unverified**. The script has no way to certify an original paper capture and
does not auto-promote either candidate. This is a **data acquisition step,
not a successful human-review or CER/WER measurement**.

For a *true* 2–10 scan evaluation, choose unrelated physically documented
paper sources with explicit owner rights and two genuinely independent
reviewers as described below. If public receipt provenance remains uncertain,
use your own physically captured paper with a real permission record instead.

## Local-only preparation workflow

1. Select **2–10 physically captured paper documents**, ideally from at
   least two distinct physical source documents. Obtain owner/reuse permission
   and check for sensitive details; do not upload private papers to GitHub.
2. Put images in a directory **outside any git checkout**, for example
   `~/private-ocr-c221/`. This tool accepts PNG/JPEG/TIFF images at most
   20 MiB and 35 million pixels each.
3. Create an intake draft with correct SHA-256s and two *empty*, private
   review sheets per source:

```sh
python -m pip install -e ".[test]"
python -m ocr_evolution.c221_audit \
  --root /private/private-ocr-c221 \
  --prepare-images scan_01.png scan_02.jpg
```

This creates `review-intake.json` and two blank reviewer JSON files in
`reviews/` per scan. **All permissions, photo provenance and human-review
flags default to false/blank.** Drafts can never accidentally pass. Files
are opened in exclusive create mode (no accidental overwrites).

4. A source owner independently inspects the paper provenance and confirms
   source rights. In `review-intake.json` for each case, fill:
   `category=korean|table|low_quality`,
   `capture_method=camera_capture|flatbed_scan`,
   `verified_physical_capture=true`,
   `human_original_document_attested=true`,
   `permission_attested=true`, a meaningful `license` or reuse basis,
   and `source_group` for the original physical document (safe ID).
   For a genuinely degraded image also provide `quality_defect`.
5. Two different **real people** separately open the actual image and type
   **the complete page** into their *different* reviewer JSON files, without
   seeing each other's transcription or copying OCR output. Each fills
   `reviewer_id`, timezone-aware `reviewed_at`, `transcription`,
   `visual_review_attested=true`,
   `blind_review_attested=true`,
   `no_ocr_assistance_attested=true`. Both image hashes must match.
   These flags are claims, not cryptographic proof.
6. Run the actual local Korean Tesseract accuracy measurement:

```sh
# Install Tesseract OCR with Korean + English language packs beforehand.
python -m ocr_evolution.c221_audit \
  --batch /private/private-ocr-c221/review-intake.json \
  --root /private/private-ocr-c221 \
  --private-output /private/private-ocr-c221/results/c221_metrics.json
```

The validator checks **every case before running OCR**. If a single image
has the wrong SHA, source rights are absent, the capture is simulated,
a reviewer is missing, timestamps are invalid, reviewers use the same name,
visual/blind/no-OCR attestations are missing, or complete transcriptions
disagree, the entire batch is **BLOCKED**. No metric is manufactured.
The solution requires manual resolution and independent re-review of
disagreements; it does not automatically choose one transcription.

## CER/WER definition and safety

- NFC-normalized Unicode reference and OCR output; strict Levenshtein
  character distance / reference character count, and tokenized word distance
  / reference word count (micro aggregated across 2–10 documents).
- Reports include per-category and per-case error counts, source-group
  digests and source-image/reference SHA-256 only. **Actual transcription,
  recognized text, file names and reviewer identities are excluded.**
- Reports are written locally in exclusive-create mode, with owner-only
  permission best effort. Outputs inside any Git worktree are refused.
- Fixed Tesseract config: `kor+eng`, PSM6 for prose/low-quality, PSM11 for
  tables. No per-test tuning, model training, merging or live-system writes.
- `promotion_eligible=false`, `independent_hidden_holdout=false`;
  development results do not establish unbiased generalization or AI
  intelligence growth.

## GitHub CI (never claims external people reviewed data)

The [C2.2.1 workflow](../.github/workflows/ocr-evolution-c221.yml) runs
strict 2–10 source, privacy, review-consistency and OCR-math contract
unit tests on Windows and Linux. Test image fixtures and identities are
**fabricated by tests and explicitly synthetic**. A separate step emits a
`BLOCKED_MISSING_INDEPENDENT_HUMAN_REVIEW_EVIDENCE` receipt with
`actual_scans=0` and `CER/WER=null`, because CI has no private
verified paper captures or verified human reviewers.

**Do not infer C2.2.1 complete from green tests.** The true
human-data collection gate stays BLOCKED until 2–10 real permissioned scans
and two actually independent full-text reviews arrive, then the fully
local-only evaluation is run and its results are inspected.

## Acceptance checklist

- [x] Separate offline two-reviewer 2–10 intake architecture
- [x] Fail-closed validation and reporting code
- [x] Windows/Linux synthetic-only contract tests (when CI green)
- [ ] 2–10 permission-checked genuine paper images provided
- [ ] Two real independent full-page reviews per image
- [ ] Actually run real-source local CER/WER and independently verify provenance
- [ ] Leakage-free blinded hidden holdout and repeatability verification
- [ ] Human authorization for any final PR merge or operational promotion

**Next choices:** secure genuine 2–10 physical document sources and independent
reviewers (C2.2.1-GT), strengthen verified source-provenance / optional
cryptographic reviewer attestations, or continue C2.3 table parsing without
promoting the blocked OCR performance claims.
