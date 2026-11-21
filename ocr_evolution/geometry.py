"""Strict, conservative table-neighbor checks from Tesseract TSV geometry.

Not TEDS. Tests require pre-verified adjacent values and actual OCR boxes.
False/ambiguous matches count as failed checks rather than guessed successes.
"""
import csv
from io import StringIO

from .metrics import normalize

DIRECTIONS = ("up", "down", "left", "right")


def read_tsv_lines(tsv):
    reader = csv.DictReader(StringIO(tsv), delimiter="\t")
    if not reader.fieldnames or not {"text", "left", "top", "width", "height",
                                     "block_num", "par_num", "line_num"}.issubset(reader.fieldnames):
        raise ValueError("invalid OCR TSV header")
    lines = {}
    for row in reader:
        value = row.get("text") or ""
        if not value.strip():
            continue
        key = (row.get("block_num"), row.get("par_num"), row.get("line_num"))
        x = int(row["left"]); y = int(row["top"])
        w = int(row["width"]); h = int(row["height"])
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            continue
        lines.setdefault(key, []).append((x, y, x + w, y + h, value))
    boxes = []
    for tokens in lines.values():
        tokens.sort(key=lambda t: t[0])
        text = " ".join(t[4] for t in tokens)
        boxes.append({"text": " ".join(normalize(text).split()),
                      "left": min(t[0] for t in tokens), "top": min(t[1] for t in tokens),
                      "right": max(t[2] for t in tokens), "bottom": max(t[3] for t in tokens)})
    return boxes


def _unique_box(boxes, target):
    # Ambiguous repeated header values cannot be confidently placed.
    target = " ".join(normalize(target).split())
    if not target:
        return None
    matches = [b for b in boxes if b["text"] == target]
    return matches[0] if len(matches) == 1 else None


def _relationship(a, b, direction):
    ax = (a["left"] + a["right"]) / 2
    bx = (b["left"] + b["right"]) / 2
    ay = (a["top"] + a["bottom"]) / 2
    by = (b["top"] + b["bottom"]) / 2
    h = max(a["bottom"] - a["top"], b["bottom"] - b["top"])
    w = max(a["right"] - a["left"], b["right"] - b["left"])
    if direction == "right":
        return bx > ax and abs(by - ay) <= h
    if direction == "left":
        return bx < ax and abs(by - ay) <= h
    if direction == "down":
        return by > ay and abs(bx - ax) <= w
    if direction == "up":
        return by < ay and abs(bx - ax) <= w
    raise ValueError("invalid direction")


def check_verified_table_adjacency(tsv, verified_tests):
    boxes = read_tsv_lines(tsv)
    checked = matched = 0
    per_direction = {key: {"checked": 0, "matched": 0} for key in DIRECTIONS}
    for item in verified_tests:
        if item.get("type") != "table" or item.get("checked") != "verified":
            raise ValueError("only verified table assertions allowed")
        anchor = _unique_box(boxes, item.get("cell", ""))
        for direction in DIRECTIONS:
            neighbor_text = item.get(direction)
            if not isinstance(neighbor_text, str) or not neighbor_text.strip():
                continue
            checked += 1
            per_direction[direction]["checked"] += 1
            neighbor = _unique_box(boxes, neighbor_text)
            if anchor and neighbor and _relationship(anchor, neighbor, direction):
                matched += 1
                per_direction[direction]["matched"] += 1
    return {"checked": checked, "matched": matched,
            "verified_direction_accuracy": matched / checked if checked else None,
            "method": "strict_text+unique_Tesseract_TSV_line_centers",
            "limits": "directional heuristic only; does NOT validate exact table grid or TEDS",
            "by_direction": per_direction}
