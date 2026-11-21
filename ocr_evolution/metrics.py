"""Strict, transparent character/word error rates for labeled OCR cases.

Distances are *not* clipped to 1: extra insertions may produce CER/WER > 1.
Unicode is NFC-normalized; whitespace is preserved for CER, tokenized for WER.
"""
from collections import defaultdict
from collections.abc import Sequence
import unicodedata

CATEGORIES = frozenset({"korean", "table", "low_quality"})


def normalize(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def edit_distance(reference: Sequence, observed: Sequence) -> int:
    """Exact Levenshtein distance using O(min(n,m)) space."""
    if len(reference) < len(observed):
        reference, observed = observed, reference
    previous = list(range(len(observed) + 1))
    for index, a in enumerate(reference, 1):
        current = [index]
        for j, b in enumerate(observed, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (a != b),
            ))
        previous = current
    return previous[-1]


def measure(expected_text: str, observed_text: str) -> dict:
    expected = normalize(expected_text)
    observed = normalize(observed_text)
    if not expected or not expected.split():
        raise ValueError("reference text must contain at least one word")
    reference_words = expected.split()
    return {
        "char_errors": edit_distance(expected, observed),
        "reference_chars": len(expected),
        "word_errors": edit_distance(reference_words, observed.split()),
        "reference_words": len(reference_words),
    }


def _aggregate(stats: list[dict]) -> dict:
    if not stats:
        raise ValueError("empty statistics")
    char_errors = sum(row["char_errors"] for row in stats)
    words_errors = sum(row["word_errors"] for row in stats)
    chars = sum(row["reference_chars"] for row in stats)
    words = sum(row["reference_words"] for row in stats)
    return {
        "count": len(stats),
        "char_errors": char_errors,
        "reference_chars": chars,
        "word_errors": words_errors,
        "reference_words": words,
        "cer": char_errors / chars,
        "wer": words_errors / words,
    }


def evaluate_predictions(records: list[dict]) -> dict:
    """Evaluate complete labeled records, without any auto-promotion decision.

    Each record needs case_id, category, expected_text and observed_text.
    All fixtures must be dev-only; a public synthetic dataset cannot pass
    as a hidden independent holdout.
    """
    if not records:
        raise ValueError("no evaluation cases")
    seen = set()
    per_category = defaultdict(list)
    details = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("case must be an object")
        case_id = record.get("case_id")
        category = record.get("category")
        split = record.get("split")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("empty or duplicate case id")
        if category not in CATEGORIES:
            raise ValueError("unknown category")
        if split != "development":
            raise ValueError("public benchmark must be development split")
        seen.add(case_id)
        stats = measure(record.get("expected_text"), record.get("observed_text"))
        per_category[category].append(stats)
        details.append({"case_id": case_id, "category": category,
                        "cer": stats["char_errors"] / stats["reference_chars"],
                        "wer": stats["word_errors"] / stats["reference_words"],
                        **stats})
    if set(per_category) != CATEGORIES:
        raise ValueError("benchmark must cover Korean, table and low-quality cases")
    return {
        "dataset_role": "synthetic_development_only",
        "overall": _aggregate([stats for values in per_category.values() for stats in values]),
        "by_category": {category: _aggregate(per_category[category])
                        for category in sorted(per_category)},
        "cases": details,
        "independent_holdout": False,
        "promotion_eligible": False,
    }
