from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_self_hosted_qemu_image_candidate import (
    CANDIDATE_PROOF_DONE,
    CANDIDATE_PROOF_START,
    boot_qemu,
    create_overlay,
    qemu_paths,
    write_candidate_proof_seed,
)
from scripts.run_self_hosted_qemu_boot_proof import run

DEFAULT_INPUT_RESULT = Path("image-build/qemu-image-candidate/qemu-candidate-20260702-result.json")
DEFAULT_OUTPUT_DIR = Path("image-artifacts/qemu-image-candidate")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qemu_img_info(path: Path) -> dict[str, Any]:
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")
    completed = run([qemu_img, "info", "--output=json", str(path)])
    return json.loads(completed.stdout)


def assert_no_backing_file(info: dict[str, Any]) -> None:
    backing_fields = (
        "backing-filename",
        "full-backing-filename",
        "backing-filename-format",
    )
    present = [field for field in backing_fields if info.get(field)]
    if present:
        raise ValueError(f"standalone image still has backing metadata: {present}")


def convert_to_standalone(*, source: Path, target: Path, compressed: bool) -> None:
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")
    if target.exists():
        target.unlink()
    command = [qemu_img, "convert", "-O", "qcow2"]
    if compressed:
        command.append("-c")
    command.extend([str(source), str(target)])
    run(command)


def run_standalone_boot_proof(
    *,
    standalone_image: Path,
    proof_dir: Path,
    run_id: str,
    owner_id: str,
    owner_slug: str,
    env_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    qemu = qemu_paths()
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_overlay = proof_dir / f"{run_id}-proof-overlay.qcow2"
    create_overlay(
        qemu_img=qemu["qemu_img"],
        backing_image=standalone_image,
        overlay=proof_overlay,
    )
    proof_seed = proof_dir / f"{run_id}-proof-seed.iso"
    write_candidate_proof_seed(
        seed_dir=proof_dir / f"{run_id}-proof-seed",
        seed_iso=proof_seed,
        run_id=run_id,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=env_name,
    )
    proof_log = boot_qemu(
        qemu=qemu["qemu"],
        code_fd=qemu["code_fd"],
        vars_template=qemu["vars_template"],
        vars_fd=proof_dir / f"{run_id}-proof-vars.fd",
        disk_image=proof_overlay,
        seed_iso=proof_seed,
        timeout_seconds=timeout_seconds,
    )
    proof_log_path = proof_dir / f"{run_id}-proof-serial.log"
    proof_log_path.write_text(proof_log)
    proof_passed = (
        CANDIDATE_PROOF_START in proof_log
        and CANDIDATE_PROOF_DONE in proof_log
        and '"schema_version": "self_hosted_core_init_result_v1"' in proof_log
        and '"schema_version": "self_hosted_core_health_check_v1"' in proof_log
        and '"status": "passed"' in proof_log
    )
    return {
        "status": "passed" if proof_passed else "failed",
        "proof_overlay": str(proof_overlay),
        "proof_seed": str(proof_seed),
        "proof_serial_log": str(proof_log_path),
        "markers": {
            "candidate_proof_start_seen": CANDIDATE_PROOF_START in proof_log,
            "candidate_proof_done_seen": CANDIDATE_PROOF_DONE in proof_log,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flatten, checksum, manifest, and boot-prove a QEMU self-hosted Core image candidate."
    )
    parser.add_argument("--candidate-result", type=Path, default=DEFAULT_INPUT_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default="qemu-standalone-20260702")
    parser.add_argument("--owner-id", default="owner_qemu_standalone_proof")
    parser.add_argument("--owner-slug", default="qemu-standalone-proof")
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--skip-boot-proof", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candidate_result_path = resolve_repo_path(args.candidate_result)
    output_dir = resolve_repo_path(args.output_dir)
    proof_dir = output_dir / "proof"
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_result = load_json(candidate_result_path)
    if candidate_result.get("status") != "passed":
        raise ValueError("candidate result must have status=passed")
    candidate_image = Path(candidate_result["candidate_image"])
    if not candidate_image.is_absolute():
        candidate_image = resolve_repo_path(candidate_image)
    if not candidate_image.is_file():
        raise ValueError(f"candidate image is missing: {candidate_image}")

    standalone_image = output_dir / f"{args.run_id}.qcow2"
    convert_to_standalone(
        source=candidate_image,
        target=standalone_image,
        compressed=not args.no_compress,
    )
    info = qemu_img_info(standalone_image)
    assert_no_backing_file(info)
    digest = sha256_file(standalone_image)
    checksum_path = output_dir / f"{standalone_image.name}.sha256"
    checksum_path.write_text(f"{digest}  {standalone_image.name}\n")

    boot_proof = None
    if not args.skip_boot_proof:
        boot_proof = run_standalone_boot_proof(
            standalone_image=standalone_image,
            proof_dir=proof_dir,
            run_id=args.run_id,
            owner_id=args.owner_id,
            owner_slug=args.owner_slug,
            env_name=args.env_name,
            timeout_seconds=args.timeout_seconds,
        )
        if boot_proof["status"] != "passed":
            raise ValueError("standalone image boot proof failed")

    manifest = {
        "schema_version": "self_hosted_qemu_image_release_manifest_v1",
        "created_at": utc_now(),
        "status": "passed",
        "run_id": args.run_id,
        "artifact_type": "standalone_qcow2_self_hosted_core_template",
        "source_candidate_result": str(candidate_result_path),
        "source_candidate_image": str(candidate_image),
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
        "boot_proof": boot_proof,
        "boundaries": [
            "synthetic owner proof only",
            "no real owner data",
            "not yet signed",
            "not yet published",
            "provider support is tracked by separate provider proof records",
        ],
    }
    manifest_path = output_dir / f"{args.run_id}-release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
