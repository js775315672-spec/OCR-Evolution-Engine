"""Fail-closed candidate evaluation; no GitHub writes or model access."""
from collections import Counter
from .evaluator import evaluate

def analyze_failures(cases):
    return {"total": len(cases),
            "mismatches": sum(x.expected != x.observed for x in cases),
            "by_split": dict(Counter(x.split for x in cases if x.expected != x.observed))}

def run_cycle(baseline, candidate, cycle_id):
    if not cycle_id or not isinstance(cycle_id, str):
        raise ValueError("cycle id required")
    result = evaluate(baseline, candidate)
    return {"cycle_id": cycle_id, "failure_analysis": analyze_failures(baseline),
            "evaluation": result,
            "decision": "CANDIDATE_ELIGIBLE_FOR_HUMAN_REVIEW" if result["approved"] else "BLOCKED",
            "applied": False, "model_weights_changed": False}
