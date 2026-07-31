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

from scripts.prove_pios_starter_disk_image_hygiene import (
    load_json,
    resolve_repo_path,
    validate_release_image,
)

EVIDENCE_SCHEMA = "pios_starter_disk_image_evidence_readiness_v1"
RELEASE_SCHEMA = "self_hosted_qemu_image_release_manifest_v1"
HYGIENE_SCHEMA = "self_hosted_pios_starter_hygiene_proof_v1"
RESIDUE_SCHEMA = "self_hosted_pios_starter_residue_inspection_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def required_true(record: dict[str, Any], keys: tuple[str, ...], description: str) -> None:
    missing = [key for key in keys if record.get(key) is not True]
    if missing:
        raise ValueError(f"{description} is missing passed markers: {', '.join(missing)}")


def normalized_path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("evidence record is missing an image or manifest path")
    return Path(value).resolve()


def validate_evidence_records(
    *,
    release_manifest: dict[str, Any],
    release_manifest_path: Path,
    fresh_hygiene: dict[str, Any],
    residue_inspection: dict[str, Any],
) -> dict[str, Any]:
    if release_manifest.get("schema_version") != RELEASE_SCHEMA:
        raise ValueError("release manifest has an unexpected schema_version")
    if release_manifest.get("status") != "passed":
        raise ValueError("release manifest must have status=passed")
    if fresh_hygiene.get("schema_version") != HYGIENE_SCHEMA:
        raise ValueError("fresh hygiene result has an unexpected schema_version")
    if fresh_hygiene.get("status") != "passed" or fresh_hygiene.get("proof", {}).get("status") != "passed":
        raise ValueError("fresh hygiene proof must have status=passed")
    if residue_inspection.get("schema_version") != RESIDUE_SCHEMA:
        raise ValueError("residue inspection result has an unexpected schema_version")
    if (
        residue_inspection.get("status") != "passed"
        or residue_inspection.get("inspection", {}).get("status") != "passed"
    ):
        raise ValueError("residue inspection must have status=passed")

    manifest_image = normalized_path(release_manifest.get("standalone_image"))
    expected_sha256 = release_manifest.get("standalone_image_sha256")
    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ValueError("release manifest is missing standalone_image_sha256")
    for proof_name, proof in (
        ("fresh hygiene", fresh_hygiene),
        ("residue inspection", residue_inspection),
    ):
        if normalized_path(proof.get("release_manifest")) != release_manifest_path.resolve():
            raise ValueError(f"{proof_name} references a different release manifest")
        release_image = proof.get("release_image")
        if not isinstance(release_image, dict):
            raise ValueError(f"{proof_name} is missing release_image")
        if normalized_path(release_image.get("image")) != manifest_image:
            raise ValueError(f"{proof_name} references a different QCOW2 image")
        if release_image.get("sha256") != expected_sha256:
            raise ValueError(f"{proof_name} references a different QCOW2 checksum")

    boot_proof = release_manifest.get("boot_proof")
    if not isinstance(boot_proof, dict) or boot_proof.get("status") != "passed":
        raise ValueError("release manifest is missing a passed package health proof")
    cleanup = release_manifest.get("residue_cleanup")
    if cleanup is not None:
        if not isinstance(cleanup, dict) or not isinstance(cleanup.get("markers"), dict):
            raise ValueError("release manifest residue cleanup is malformed")
        required_true(
            cleanup["markers"],
            ("cleanup_start_seen", "cleanup_done_seen"),
            "residue cleanup",
        )
    proof_markers = fresh_hygiene.get("proof", {}).get("markers")
    if not isinstance(proof_markers, dict):
        raise ValueError("fresh hygiene proof is missing markers")
    required_true(
        proof_markers,
        (
            "proof_start_seen",
            "empty_core_state_seen",
            "health_schema_seen",
            "health_passed_seen",
            "proof_done_seen",
        ),
        "fresh hygiene proof",
    )
    residue_markers = residue_inspection.get("inspection", {}).get("markers")
    if not isinstance(residue_markers, dict):
        raise ValueError("residue inspection is missing markers")
    required_true(
        residue_markers,
        ("inspection_start_seen", "inspection_passed_seen"),
        "residue inspection",
    )
    if residue_markers.get("inspection_failed_seen") is not False:
        raise ValueError("residue inspection reported a failure marker")
    return {
        "release_image": str(manifest_image),
        "release_image_sha256": expected_sha256,
        "package_health_proof": "passed",
        "fresh_vm_hygiene": "passed",
        "residue_inspection": "passed",
        "residue_cleanup": "passed" if cleanup is not None else "not_applicable",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that one PIOS Starter Disk Image has matching passed package-health, "
            "fresh-VM hygiene, and residue-inspection evidence. This does not sign or publish it."
        )
    )
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--fresh-hygiene-result", type=Path, required=True)
    parser.add_argument("--residue-inspection-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    release_manifest_path = resolve_repo_path(args.release_manifest)
    hygiene_path = resolve_repo_path(args.fresh_hygiene_result)
    residue_path = resolve_repo_path(args.residue_inspection_result)
    output_path = resolve_repo_path(args.output)
    release_manifest = load_json(release_manifest_path)
    release_image = validate_release_image(release_manifest, release_manifest_path)
    summary = validate_evidence_records(
        release_manifest=release_manifest,
        release_manifest_path=release_manifest_path,
        fresh_hygiene=load_json(hygiene_path),
        residue_inspection=load_json(residue_path),
    )
    if summary["release_image"] != release_image["image"]:
        raise ValueError("release manifest image changed during evidence validation")
    result = {
        "schema_version": EVIDENCE_SCHEMA,
        "created_at": utc_now(),
        "status": "passed",
        "readiness": "local_image_evidence_complete",
        "release_manifest": str(release_manifest_path),
        "fresh_hygiene_result": str(hygiene_path),
        "residue_inspection_result": str(residue_path),
        "summary": summary,
        "remaining_separate_gates": [
            "signing ceremony approval and protected production key use",
            "public release manifest, checksums, release notes, and publication approval",
            "provider support remains governed by separate provider proof records",
        ],
        "boundaries": [
            "local evidence validation only",
            "does not sign, publish, import, deploy, or create cloud resources",
            "does not perform Owner Bind or create owner-specific state",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
