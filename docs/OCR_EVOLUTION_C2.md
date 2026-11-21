# C2: Korean, table and low-quality OCR evaluation

## Status and trust boundary

This is an **original, open, synthetic development dataset** with six deliberately
simple reference pages (two Korean prose, two 3-column Korean tables, two
artificially degraded scans). No human-annotated scan corpus, user uploads,
holdout observations or protected agent datasets are included. The repository
is independent from Ouroboros, Cerberus and Fenrir. Evaluation is read-only:
it does not change OCR weights or approve an autonomous improvement.

## Input contract

`benchmarks/c2_synthetic_manifest.json` is UTF-8 JSON, schema_version=1,
source=original_synthetic_fixtures, license=CC0-1.0, split=development.
Every case has a unique safe `case_id`, category
`korean | table | low_quality`, and nonempty `expected_text`. Table
references have exactly three tab-delimited columns on every line.
The generator rejects invalid IDs, missing categories, duplicate IDs, invalid
splits, and empty/oversized references. Images are generated on the CI runner
rather than shipped from an unknown external dataset.

## Measurement

- Character error rate (CER) = total Levenshtein character operations /
  total reference Unicode code points; NFC normalization is applied.
  Exact reference whitespace is counted, including table layout separators.
- Word error rate (WER) = total Levenshtein operations on whitespace-tokenized
  words / total reference words.
- Metrics are **micro-aggregated** across cases and reported by category,
  including raw error counts, denominators and per-case scores.
- CER/WER can exceed 1 if many insertions occur; values are not clipped.
- Word-level table cell boundaries and actual layout quality are **not**
  fully represented by CER/WER. Future table structure accuracy must be
  measured separately.
- Missing predictions must fail evaluation; never silently drop difficult
  cases. The benchmark runs Tesseract 6/6 times, recording empty outputs
  as errors rather than omitted results.
- Layout configuration: Tesseract PSM 6 is used for Korean prose and degraded
  prose, while PSM 11 (sparse text) is used for table grids. This is a
  **development-set-selected** heuristic, not an unbiased improvement claim.
  Each case records the mode used. Baseline run 44925077811 (PSM 6 for all
  cases) returned empty output for both table examples (table CER/WER 1.0).

## Reproduce on Ubuntu

Install `tesseract-ocr tesseract-ocr-eng tesseract-ocr-kor fonts-nanum fontconfig`.
Then:

```sh
python -m pip install -e '.[benchmark]'
FONT="$(fc-match -f '%{file}' 'NanumGothic')"
python -m ocr_evolution.benchmark --font "$FONT" \
  --manifest benchmarks/c2_synthetic_manifest.json --out-dir reports/c2
cat reports/c2/results.md
```

Windows and Linux contract tests: `python -m pip install -e '.[test]'` then
`python -m unittest discover -s tests -p test_c2_metrics.py -v`.

Results are written to `reports/c2/results.json`, `reports/c2/results.md`
and `reports/c2/images/*.png` during CI; the artifact is
`c2-synthetic-dev-ocr-results`. JSON contains exact reference/observed
strings, per-case measures, image SHA-256, manifest SHA-256, git SHA, run ID,
font name and Tesseract version string (when available).
No generated files are committed to the repository.

## Safety gates and next step

The C1 evaluation gate may approve only a genuinely separate immutable
holdout with provenance and independent reference annotations. This public
synthetic development set **must never** be used as proof of self-improvement
or to tune and then evaluate the same candidate.

C3 prerequisites: licensed real Korean document images, human-audited ground
truth, duplicate/source leakage screening, train/dev/hidden holdout split,
corpus hashes and access boundaries, CER/WER and table-cell structural metric
baseline, time/quality trade-off, independent replayable provenance, and
explicit user approval before any production promotion. PRs remain Draft.
