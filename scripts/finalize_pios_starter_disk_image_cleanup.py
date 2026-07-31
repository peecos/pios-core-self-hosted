from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.clean_pios_starter_disk_image_residue import CLEANUP_DONE, CLEANUP_START
from scripts.package_self_hosted_qemu_image_candidate import (
    assert_no_backing_file,
    qemu_img_info,
    run_standalone_boot_proof,
    sha256_file,
)
from scripts.prove_pios_starter_disk_image_hygiene import (
    load_json,
    resolve_repo_path,
    validate_release_image,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_cleanup_log(path: Path) -> dict[str, bool]:
    if not path.is_file():
        raise ValueError(f"cleanup serial log is missing: {path}")
    text = path.read_text(errors="replace")
    markers = {
        "cleanup_start_seen": CLEANUP_START in text,
        "cleanup_done_seen": CLEANUP_DONE in text,
    }
    if not all(markers.values()):
        raise ValueError(f"cleanup serial log does not prove completion: {markers}")
    return markers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize a PIOS Starter replacement after a previously completed narrow residue-cleanup "
            "overlay by running the synthetic health proof and writing a release manifest."
        )
    )
    parser.add_argument("--source-release-manifest", type=Path, required=True)
    parser.add_argument("--cleaned-image", type=Path, required=True)
    parser.add_argument("--cleanup-serial-log", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--owner-id", default="owner_pios_starter_cleanup_proof")
    parser.add_argument("--owner-slug", default="pios-starter-cleanup-proof")
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_manifest_path = resolve_repo_path(args.source_release_manifest)
    cleaned_image = resolve_repo_path(args.cleaned_image)
    cleanup_serial_log = resolve_repo_path(args.cleanup_serial_log)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_manifest = load_json(source_manifest_path)
    source_release = validate_release_image(source_manifest, source_manifest_path)
    if not cleaned_image.is_file():
        raise ValueError(f"cleaned image is missing: {cleaned_image}")
    cleanup_markers = validate_cleanup_log(cleanup_serial_log)
    info = qemu_img_info(cleaned_image)
    if info.get("format") != "qcow2":
        raise ValueError(f"cleaned image must use qcow2 format, got {info.get('format')}")
    assert_no_backing_file(info)
    digest = sha256_file(cleaned_image)
    checksum_path = output_dir / f"{cleaned_image.name}.sha256"
    checksum_path.write_text(f"{digest}  {cleaned_image.name}\n")

    proof = run_standalone_boot_proof(
        standalone_image=cleaned_image,
        proof_dir=output_dir / "proof",
        run_id=args.run_id,
        owner_id=args.owner_id,
        owner_slug=args.owner_slug,
        env_name=args.env_name,
        timeout_seconds=args.timeout_seconds,
    )
    if proof["status"] != "passed":
        raise ValueError("replacement standalone image health proof failed")

    result = {
        "schema_version": "self_hosted_qemu_image_release_manifest_v1",
        "created_at": utc_now(),
        "status": "passed",
        "run_id": args.run_id,
        "artifact_type": "standalone_qcow2_self_hosted_core_template",
        "source_release_manifest": str(source_manifest_path),
        "source_release_image": source_release["image"],
        "source_candidate_result": source_manifest.get("source_candidate_result"),
        "source_candidate_image": source_manifest.get("source_candidate_image"),
        "standalone_image": str(cleaned_image),
        "standalone_image_name": cleaned_image.name,
        "standalone_image_sha256": digest,
        "standalone_image_checksum_file": str(checksum_path),
        "qemu_img_info": info,
        "inspection": {
            "format": info.get("format"),
            "virtual_size": info.get("virtual-size"),
            "actual_size": info.get("actual-size"),
            "backing_file_present": False,
        },
        "residue_cleanup": {
            "removed_path": "/mnt/pios-seed",
            "cleanup_serial_log": str(cleanup_serial_log),
            "markers": cleanup_markers,
        },
        "boot_proof": proof,
        "boundaries": [
            "removed only the empty /mnt/pios-seed temporary build directory",
            "source image unchanged",
            "disposable cleanup and proof overlays only",
            "synthetic owner proof only",
            "no real owner data",
            "not yet signed",
            "not yet published",
        ],
    }
    result_path = output_dir / f"{args.run_id}-release-manifest.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
