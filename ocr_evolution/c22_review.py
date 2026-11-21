"""C2.2 two-reviewer transcription acceptance for local, permissioned images.

OCR suggestions are explicitly not ground truth. Attestations are claims by
reviewers, not cryptographic proof; no auto-approval, promotion, or upload.
"""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from .metrics import normalize
from .real_corpus import _local_image

ID = re.compile(r"^[a-z][a-z0-9_]{2,60}$")


def _attestation(value, image_sha):
    if not isinstance(value, dict) or value.get("image_sha256") != image_sha:
        raise ValueError("reviewer must reference exact image digest")
    identity = value.get("reviewer_id")
    text = value.get("transcription")
    if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,80}", identity):
        raise ValueError("named reviewer id required")
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ValueError("complete, nonempty reviewed transcription required")
    if value.get("visual_review_attested") is not True:
        raise ValueError("visual review attestation required")
    timestamp = value.get("reviewed_at")
    if not isinstance(timestamp, str):
        raise ValueError("review time required")
    try:
        if datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise ValueError("valid ISO 8601 review timestamp required") from exc
    return identity, normalize(text)


def adjudicate(image_sha, reviewer_records):
    """Accept only two independent, matching, visual attestations.

    Simple reviewer IDs are auditable metadata, not identity verification.
    A separate audit must confirm identities before external publication.
    """
    if not isinstance(image_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", image_sha):
        raise ValueError("invalid SHA-256")
    if not isinstance(reviewer_records, list) or len(reviewer_records) != 2:
        raise ValueError("two independent reviewers required")
    a_id, a_text = _attestation(reviewer_records[0], image_sha)
    b_id, b_text = _attestation(reviewer_records[1], image_sha)
    if a_id == b_id:
        raise ValueError("two distinct reviewer identities required")
    if a_text != b_text:
        raise ValueError("reviewers disagree; human adjudication required")
    return {"text": a_text, "reference_sha256": sha256(a_text.encode("utf-8")).hexdigest(),
            "reviewer_ids": sorted([a_id, b_id]),
            "review_status": "two_reviewers_agree_unverified_identities"}


def build_local_manifest(request: dict, image_root: Path) -> dict:
    """Prepare C2.1 local manifest after manual source/quality authentication."""
    cases = request.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("invalid case count")
    out, ids, hashes = [], set(), set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not ID.fullmatch(case_id) or case_id in ids:
            raise ValueError("unsafe or duplicate case ID")
        file = _local_image(image_root, case.get("image"))
        digest = sha256(file.read_bytes()).hexdigest()
        if digest != case.get("sha256") or digest in hashes:
            raise ValueError("tampered or duplicate image")
        if case.get("verified_physical_capture") is not True:
            raise ValueError("photo/scan origin not independently confirmed")
        if case.get("capture_method") not in ("camera_capture", "flatbed_scan"):
            raise ValueError("physical capture method must be verified")
        if case.get("category") not in ("korean", "table", "low_quality"):
            raise ValueError("invalid category")
        if case.get("permission_attested") is not True:
            raise ValueError("image owner permission required")
        if not isinstance(case.get("license"), str) or not case["license"].strip():
            raise ValueError("source rights missing")
        decision = adjudicate(digest, case.get("reviews"))
        # Keep reviewer identities out of CI/public artifacts.
        out.append({"case_id": case_id, "image": case["image"], "sha256": digest,
                    "category": case["category"],
                    "capture_method": case["capture_method"],
                    "provenance_kind": "user_owned_local",
                    "permission_attested": True, "license": case["license"],
                    "transcription": decision["text"],
                    "transcription_quality": "human_checked_full"})
        ids.add(case_id)
        hashes.add(digest)
    return {"schema_version": 1, "public_split": "development", "cases": out,
            "promotion_eligible": False,
            "review_scope": "two human claims; identity authenticity not cryptographically verified"}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-request", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.review_request.read_text(encoding="utf-8"))
    result = build_local_manifest(data, args.image_root)
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print("Local-only audited manifest prepared for", len(result["cases"]), "scans")


if __name__ == "__main__":
    main()
