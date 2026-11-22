# OCR Evolution C1 — independent improvement gate

Scope: this repository only. Never import Ouroboros, Cerberus or Fenrir code, credentials, ledgers or evaluation sets.

Pipeline: immutable baseline -> failure analysis -> candidate proposal (external, untrusted) -> isolated holdout evaluation -> regression gate -> human review. No automatic promotion, merging, OCR model retraining or production deployment.

Evaluation contract: unique case IDs, identical ground truth and split, holdout-only, normalized character similarity mean, minimum gain 0.01 and maximum per-case regression 0.02. Any mismatched evidence raises an error; blocked candidates never apply.

Current limitations: synthetic unit fixtures only; no real Korean, table, low-quality or adversarial OCR benchmark; no actual autonomous candidate generator, persistent append-only ledger, signed CI provenance, speed/latency comparison or measured multi-cycle gains. The word 'evolution' does not establish intelligence improvement.

Next gate: collect licensed ground-truth corpus, split train/dev/hidden holdout by document source, add CER/WER/table metrics, provenance and cost budgets; then run 3+ independent cycles and report failed as well as successful candidates.
