"""Fail-closed structural scoring for OCR-produced rectangular tables.

Text alone is NOT a table prediction. A caller must supply row/column-aligned
cells from a real document parsing step; we never infer structure from ground truth.
"""
from .metrics import normalize

def validate_grid(grid, *, allow_empty=False):
    if not isinstance(grid, list) or (not grid and not allow_empty):
        raise ValueError("table grid must be a nonempty row list")
    width = None
    total = 0
    for row in grid:
        if not isinstance(row, list) or not row or any(not isinstance(x, str) for x in row):
            raise ValueError("table rows must contain strings")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("ragged table is unsupported; merged cells need explicit span schema")
        total += len(row)
        if total > 5000:
            raise ValueError("table is too large")
    return [[normalize(x).strip() for x in row] for row in grid]


def _f1(gold, predicted):
    matched = len(gold & predicted)
    return {
        "expected": len(gold), "predicted": len(predicted),
        "matched": matched,
        "precision": matched / len(predicted) if predicted else 0.0,
        "recall": matched / len(gold) if gold else 0.0,
        "f1": 2 * matched / (len(gold) + len(predicted)) if (gold or predicted) else 0.0,
    }


def _features(grid):
    cells = set()
    adjacency = set()
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            cells.add((r, c, value))
            if c + 1 < len(row):
                adjacency.add(("right", r, c, value, row[c + 1]))
            if r + 1 < len(grid):
                adjacency.add(("down", r, c, value, grid[r + 1][c]))
    return cells, adjacency


def score_grid(expected, predicted):
    """Two independent exact metrics: positioned cells and adjacency edges.

    A flat-text OCR output must pass predicted=None, in which case table
    structure is unmeasured (not zero and not a pass).
    """
    gt = validate_grid(expected)
    if predicted is None:
        return {
            "available": False,
            "reason": "engine did not emit row/column-structured table cells",
            "cell": None, "adjacency": None,
        }
    candidate = validate_grid(predicted, allow_empty=True)
    true_cells, true_edges = _features(gt)
    pred_cells, pred_edges = _features(candidate)
    return {"available": True, "cell": _f1(true_cells, pred_cells),
            "adjacency": _f1(true_edges, pred_edges),
            "expected_shape": [len(gt), len(gt[0])],
            "predicted_shape": [len(candidate), len(candidate[0]) if candidate else 0]}
