"""Download only previously hash-verified public receipt candidates to local PRIVATE space.

This is NOT a two-person human review, not proof of physical capture, and not
permission to upload source images to GitHub. Offline evaluation remains BLOCKED.
"""
import argparse
import json
import os
from pathlib import Path
import re
from hashlib import sha256

from PIL import Image

DATASET = "HumynLabs/Korean_Receipts_Dataset"
EXPECTED_ROLE = "actual_public_image_intake_unreviewed_not_a_real_scan_benchmark"


def _private_directory(out_dir: Path):
    result = out_dir.resolve()
    for parent in (result, *result.parents):
        if (parent / ".git").exists():
            raise ValueError("source scans and reviews cannot be stored within a Git checkout")
    if out_dir.exists() or out_dir.is_symlink():
        raise FileExistsError("private output must be a new non-existing directory")
    return result


def validate_queue(queue):
    if not isinstance(queue, dict) or queue.get("schema_version") != 1:
        raise ValueError("invalid source queue")
    if queue.get("role") != EXPECTED_ROLE or queue.get("upstream_dataset") != DATASET:
        raise ValueError("source provenance contract mismatch")
    revision = queue.get("upstream_commit")
    if not isinstance(revision, str) or not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("immutable dataset commit SHA required")
    if queue.get("upstream_license_claim") != "CC-BY-4.0":
        raise ValueError("source usage terms not confirmed")
    if queue.get("per_image_physical_capture_verified") is not False:
        raise ValueError("this intake is NOT a verified physical paper scan")
    if queue.get("two_independent_human_full_transcripts") != 0:
        raise ValueError("no real independent reviewers provided for this intake")
    if queue.get("independent_holdout") is not False or queue.get("promotion_eligible") is not False:
        raise ValueError("candidate intake must never be used for model promotion")
    cases = queue.get("cases")
    if not isinstance(cases, list) or not 2 <= len(cases) <= 10:
        raise ValueError("expected 2-10 intake candidates")
    names, hashes = set(), set()
    for c in cases:
        if not isinstance(c, dict):
            raise ValueError("invalid case")
        filename = c.get("upstream_path")
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9 _.-]{3,140}",filename):
            raise ValueError("unsafe source path")
        if filename in names or c.get("sha256") in hashes:
            raise ValueError("duplicated case image")
        digest = c.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}",digest):
            raise ValueError("invalid source SHA")
        if c.get("physical_capture_evidence") != "NOT_VERIFIED" or c.get("human_review_evidence") != "NOT_PROVIDED":
            raise ValueError("unverified human/physical claims must not be forged")
        if c.get("cer") is not None or c.get("wer") is not None:
            raise ValueError("no ground truth, no CER/WER")
        if c.get("status") != "BLOCKED_UNVERIFIED_PHYSICAL_ORIGIN_AND_HUMAN_GT":
            raise ValueError("unreviewed source state tampered")
        names.add(filename)
        hashes.add(digest)
    return revision, cases


def stage_verified_candidates(queue: dict, dest: Path, downloader=None):
    """Actual public dataset files only; enforce exact prior independent run hashes."""
    if os.getenv("OCR_C221_EXTERNAL_DATA_CONSENT") != "1":
        raise RuntimeError("external source download requires consent flag")
    revision, cases = validate_queue(queue)
    _private_directory(dest)
    if downloader is None:
        from huggingface_hub import hf_hub_download
        downloader = hf_hub_download
    # Verify ALL files and their bytes before copying any to the destination.
    staged = []
    for case in cases:
        source = Path(downloader(repo_id=DATASET, repo_type="dataset",
                                 filename=case["upstream_path"], revision=revision))
        if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("source download missing or oversized")
        data = source.read_bytes()
        if sha256(data).hexdigest() != case["sha256"] or len(data) != case["image_bytes"]:
            raise ValueError("download not identical to original independently checked image")
        with Image.open(source) as opened:
            if opened.format != case["decoded_format"]:
                raise ValueError("decoded source format drift")
            if opened.size != (case["width"],case["height"]):
                raise ValueError("source image dimension drift")
            opened.verify()
        staged.append((case, data))
    dest.mkdir(parents=True,exist_ok=False)
    dest.chmod(0o700)
    for index,(case,data) in enumerate(staged,1):
        path = dest / ("receipt_candidate_%02d.%s" % (index,"jpg"))
        with path.open("xb") as f:
            f.write(data)
        path.chmod(0o600)
    status={"source_images_checked":len(staged),
            "permission_basis":"upstream CC-BY-4.0 attribution required",
            "source_revision":revision,
            "physical_capture_verified":False,
            "two_independent_full_human_transcriptions":0,
            "actual_paper_scan_cer":None,"actual_paper_scan_wer":None,
            "promotion_eligible":False,
            "gate":"BLOCKED_PENDING_REAL_CAPTURE_PROOF_AND_2_HUMAN_FULL_TRANSCRIPTS"}
    (dest / "REVIEW_STATUS.json").write_text(json.dumps(status,indent=2)+"\n",encoding="utf-8")
    return status


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",type=Path,default=Path("benchmarks/c221_real_receipt_review_queue.json"))
    p.add_argument("--private-dir",type=Path,required=True)
    args=p.parse_args()
    queue=json.loads(args.queue.read_text(encoding="utf-8"))
    status=stage_verified_candidates(queue,args.private_dir)
    print(json.dumps(status,ensure_ascii=False,sort_keys=True))


if __name__ == "__main__":
    main()
