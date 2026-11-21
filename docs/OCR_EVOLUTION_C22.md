# C2.2 — 실제 촬영 한국어 OCR · 수동 전사 정답 검증 게이트

This phase expands the existing Draft PR #2. The OCR repository, its data,
workflows, revisions and review records are independent of Ouroboros, Cerberus
and Fenrir. No writes to `main`, no merges, no model promotion and no external
GitHub Actions write permissions.

## Sources and evidence classifications

| Source | Evidence | Rights | Ground truth | Scope |
|---|---|---|---|---|
| [hoonisone/K-STR-Bench](https://huggingface.co/datasets/hoonisone/K-STR-Bench) GIST-Signboard only | Real Korean camera photographs of signs, with published author-reviewed labels | CC BY 4.0 for GIST subset only | Published image-crop labels, not independently re-reviewed in this project | CER/WER of 3 cropped real-world Korean text regions; **not a receipt/document scan** |
| [HumynLabs/Korean_Receipts_Dataset](https://huggingface.co/datasets/HumynLabs/Korean_Receipts_Dataset) | 20 Korean receipts (two are acquired in CI); dataset mixes collected, crowdsourced and simulated receipts | CC BY 4.0 | **No full human transcript provided** | Intake only; real-vs-simulated origin **unverified per image**; CER/WER **N/A** |
| KORIE (MahmoudSalah) | Korean photographed/scanned receipt images + scholarly annotations | Explicit reuse permission not confirmed on the repository | Published transcriptions | **Not auto-downloaded or copied** until terms confirmed |

Do not call photo-style simulated images physical scans. Do not call a publisher
label a newly audited two-person ground truth. Do not confuse full receipt
recognition with cropped signboard text recognition.

The C2.2 public-source script pins both Hugging Face dataset revisions as full
SHA-1 commit IDs. K-STR-Bench publishes the GIST cropped images inside
`GIST_Signboard/text_images.tar` rather than individual HF paths; the runner
verifies archive size (maximum 750 MiB), fetches this pinned one archive only
if necessary, and safely extracts ONLY three permitted Korean crop members
without trusting tar paths. It then downloads the two receipt images. This is
more network transfer than individual image access and is a C2.2 cost limit.
It uses these five selected input images in the CI
ephemeral runner, verifies their format/dimensions, and records per-image
SHA-256, license, author attribution and reference source. **No source image,
personal receipt text, unredacted OCR output or full human transcription is
uploaded to artifacts.** Hashes, error counts and summary metrics only.

```sh
# Linux: apt install tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng
python -m pip install -e '.[test]'
python -m pip install 'huggingface_hub>=0.34,<2'
OCR_C22_EXTERNAL_DATA_CONSENT=1 python -m ocr_evolution.c22_public --output-dir reports/c22
```

The accuracy metric on real camera signboard crops is NFC Unicode
Levenshtein CER/WER, aggregated using reference character and word counts.
Results cannot be generalized to actual camera receipts or scanned paper.
No hidden holdout was established, and dataset examples have been seen.

## Local real physical capture: two independent human reviews

For physical paper photos/scans **controlled by the user**, create a private
folder containing JPEG/PNG/TIFF, and have two people look directly at each
image to independently type the complete page (not OCR text). Record their
separate reviewer IDs and ISO timezone-aware review times. Keep private
images and transcriptions **off GitHub**.

The local `c22_review` gate requires:

- Source image SHA-256 matching the actual local file, source rights and
  permission attestation.
- `verified_physical_capture:true` and `capture_method:camera_capture`
  or `flatbed_scan` independently confirmed (never guessed from appearance).
- Two distinct named human reviewers, each attesting visual review of the
  same image digest, the *entire* text and the review time. Text must match
  exactly after Unicode NFC normalization. Any disagreement blocks scoring
  until a separate manual adjudication.
- Exact case IDs and no duplicate image hashes.

Example **template only** (replace placeholder image digest and transcription
after the reviewers inspect a real source):

```json
{
  "cases": [{
    "case_id": "scan_001",
    "image": "scan_001.png",
    "sha256": "64_DIGIT_HEX_SHA256_OF_REAL_IMAGE",
    "category": "korean",
    "capture_method": "camera_capture",
    "verified_physical_capture": true,
    "permission_attested": true,
    "license": "photo owner approved local OCR evaluation",
    "reviews": [
      {
        "reviewer_id": "actual_reviewer_one",
        "image_sha256": "64_DIGIT_HEX_SHA256_OF_REAL_IMAGE",
        "transcription": "full human-typed transcription",
        "visual_review_attested": true,
        "reviewed_at": "2026-11-22T09:00:00+09:00"
      },
      {
        "reviewer_id": "actual_reviewer_two",
        "image_sha256": "64_DIGIT_HEX_SHA256_OF_REAL_IMAGE",
        "transcription": "full human-typed transcription",
        "visual_review_attested": true,
        "reviewed_at": "2026-11-22T10:00:00+09:00"
      }
    ]
  }]
}
```

```sh
python -m ocr_evolution.c22_review \
  --review-request /private/ocr/reviews.json \
  --image-root /private/ocr \
  --out-manifest /private/ocr/audited_manifest.json

python -m ocr_evolution.real_corpus \
  --manifest /private/ocr/audited_manifest.json \
  --corpus-root /private/ocr \
  --output /private/ocr/reports/measured.json
```

The reviewer names are *attestations*, **not cryptographic proof of identity**.
An external reviewer/audit should independently verify identity and
completeness before any performance claims or research publication.

CER/WER reported by `real_corpus` covers only accepted complete page
transcriptions. Missing ground truth remains null, never zero. The existing
runbook also supports sample-level source URLs for permitted public images.

## Completion gates

1. CI Windows/Linux source-security, two-reviewer and metric tests PASS.
2. Source network run PASS with real K-STR camera crops (attributed) and
   reproducible source SHA/revision; report concrete CER/WER.
3. Humyn receipt images downloaded and hashed as candidate inputs, **not yet
   physically classified or given human verified transcriptions**.
4. Full real physically scanned Korean document CER/WER remains **BLOCKED**
   until an authorized owner and two real reviewers submit a complete, verified
   scan/annotation pair; a generated or source OCR draft cannot count as GT.
5. No cross-project tool access, no auto-merge, no model promotions.

Next: independently validate at least 10 physically scanned pages by document
source with blinded reviewers; add capture-quality metadata and a proper
structure-aware table parser; retain evaluation source-group holdouts.
