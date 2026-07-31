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

from scripts.build_self_hosted_qemu_image_candidate import (
    boot_qemu,
    create_overlay,
    make_seed_iso,
    qemu_paths,
)
from scripts.package_self_hosted_qemu_image_candidate import (
    assert_no_backing_file,
    convert_to_standalone,
    qemu_img_info,
    run_standalone_boot_proof,
    sha256_file,
)
from scripts.prove_pios_starter_disk_image_hygiene import (
    load_json,
    resolve_repo_path,
    validate_release_image,
)

DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-disk-image-clean")
CLEANUP_START = "PIOS_STARTER_RESIDUE_CLEANUP_START"
CLEANUP_DONE = "PIOS_STARTER_RESIDUE_CLEANUP_DONE"
TEMPORARY_MOUNT_DIRECTORY = "/mnt/pios-seed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def build_cleanup_user_data() -> str:
    return (
        "#cloud-boothook\n"
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "trap 'sync; shutdown -h now' EXIT\n"
        f"echo {CLEANUP_START} | tee /dev/console\n"
        f"test -d {TEMPORARY_MOUNT_DIRECTORY}\n"
        f"rmdir {TEMPORARY_MOUNT_DIRECTORY}\n"
        f"test ! -e {TEMPORARY_MOUNT_DIRECTORY}\n"
        f"sync\necho {CLEANUP_DONE} | tee /dev/console\n"
    )


def run_cleanup(
    *, source_image: Path, output_dir: Path, run_id: str, timeout_seconds: int
) -> dict[str, Any]:
    qemu = qemu_paths()
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_overlay = output_dir / f"{run_id}-cleanup-overlay.qcow2"
    create_overlay(qemu_img=qemu["qemu_img"], backing_image=source_image, overlay=cleanup_overlay)
    seed_iso = output_dir / f"{run_id}-cleanup-seed.iso"
    make_seed_iso(
        seed_dir=output_dir / f"{run_id}-cleanup-seed",
        seed_iso=seed_iso,
        user_data=build_cleanup_user_data(),
        meta_data=f"instance-id: pios-starter-cleanup-{run_id}\nlocal-hostname: pios-starter-cleanup\n",
    )
    serial_log_path = output_dir / f"{run_id}-cleanup-serial.log"
    serial_log = boot_qemu(
        qemu=qemu["qemu"],
        code_fd=qemu["code_fd"],
        vars_template=qemu["vars_template"],
        vars_fd=output_dir / f"{run_id}-cleanup-vars.fd",
        disk_image=cleanup_overlay,
        seed_iso=seed_iso,
        timeout_seconds=timeout_seconds,
        live_log_path=serial_log_path,
        stop_when_seen=CLEANUP_DONE,
    )
    serial_log_path.write_text(serial_log)
    passed = CLEANUP_START in serial_log and CLEANUP_DONE in serial_log
    return {
        "status": "passed" if passed else "failed",
        "cleanup_overlay": str(cleanup_overlay),
        "seed_iso": str(seed_iso),
        "serial_log": str(serial_log_path),
        "removed_path": TEMPORARY_MOUNT_DIRECTORY,
        "markers": {
            "cleanup_start_seen": CLEANUP_START in serial_log,
            "cleanup_done_seen": CLEANUP_DONE in serial_log,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create and prove a replacement PIOS Starter Disk Image after removing only the "
            "known empty temporary /mnt/pios-seed build directory on a disposable overlay."
        )
    )
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--owner-id", default="owner_pios_starter_cleanup_proof")
    parser.add_argument("--owner-slug", default="pios-starter-cleanup-proof")
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--no-compress", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"pios-starter-clean-{utc_now_compact()}"
    manifest_path = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_manifest = load_json(manifest_path)
    source_release = validate_release_image(source_manifest, manifest_path)
    cleanup = run_cleanup(
        source_image=Path(source_release["image"]),
        output_dir=output_dir,
        run_id=run_id,
        timeout_seconds=args.timeout_seconds,
    )
    if cleanup["status"] != "passed":
        raise ValueError("temporary-directory cleanup did not complete")

    standalone_image = output_dir / f"{run_id}.qcow2"
    convert_to_standalone(
        source=Path(cleanup["cleanup_overlay"]),
        target=standalone_image,
        compressed=not args.no_compress,
    )
    info = qemu_img_info(standalone_image)
    assert_no_backing_file(info)
    digest = sha256_file(standalone_image)
    checksum_path = output_dir / f"{standalone_image.name}.sha256"
    checksum_path.write_text(f"{digest}  {standalone_image.name}\n")

    proof = run_standalone_boot_proof(
        standalone_image=standalone_image,
        proof_dir=output_dir / "proof",
        run_id=run_id,
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
        "run_id": run_id,
        "artifact_type": "standalone_qcow2_self_hosted_core_template",
        "source_release_manifest": str(manifest_path),
        "source_candidate_result": source_manifest.get("source_candidate_result"),
        "source_candidate_image": source_manifest.get("source_candidate_image"),
        "standalone_image": str(standalone_image),
        "standalone_image_name": standalone_image.name,
        "standalone_image_sha256": digest,
        "standalone_image_checksum_file": str(checksum_path),
        "qemu_img_info": info,
        "inspection": {
            "format": info.get("format"),
            "virtual_size": info.get("virtual-size"),
            "actual_size": info.get("actual-size"),
            "backing_file_present": False,
        },
        "residue_cleanup": cleanup,
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
    result_path = output_dir / f"{run_id}-release-manifest.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
