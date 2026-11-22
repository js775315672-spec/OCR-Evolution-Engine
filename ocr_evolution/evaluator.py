"""Deterministic, independent OCR candidate scoring and safety gates."""
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
import json

@dataclass(frozen=True)
class Case:
    case_id: str
    expected: str
    observed: str
    split: str = "holdout"

def score(cases):
    if not cases:
        raise ValueError("evaluation set must not be empty")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case id")
    return sum(SequenceMatcher(None, c.expected, c.observed).ratio() for c in cases) / len(cases)

def evaluate(baseline, candidate, *, min_gain=0.01, max_regression=0.02):
    if not baseline or not candidate:
        raise ValueError("missing cases")
    b = {c.case_id: c for c in baseline}
    c = {x.case_id: x for x in candidate}
    if b.keys() != c.keys() or any(b[k].expected != c[k].expected or b[k].split != c[k].split for k in b):
        raise ValueError("baseline/candidate dataset mismatch")
    if any(x.split != "holdout" for x in baseline):
        raise ValueError("only independent holdout data may approve candidates")
    before, after = score(baseline), score(candidate)
    regressions = [k for k in b if score([c[k]]) + max_regression < score([b[k]])]
    approved = after - before >= min_gain and not regressions
    evidence = {"baseline": before, "candidate": after, "gain": after-before,
                "regression_case_ids": sorted(regressions), "approved": approved,
                "dataset_sha256": sha256(json.dumps(
                    sorted((x.case_id, x.expected, x.split) for x in baseline),
                    ensure_ascii=False).encode()).hexdigest()}
    return evidence
