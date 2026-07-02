from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SIGNING_PROOF = Path(
    "image-artifacts/qemu-release-signing/"
    "pios-core-self-hosted-qemu-arm64-20260702/release-signing-proof.json"
)
DEFAULT_VALIDATION_RESULT = Path(
    "image-artifacts/qemu-release-package/"
    "pios-core-self-hosted-qemu-arm64-20260702-validation-result.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/qemu-public-release")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def public_build_artifact_ref(path: Path) -> str:
    name = path.name
    if name:
        return f"build-artifacts/{name}"
    return "build-artifacts/unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a public-facing release manifest from the local QEMU self-hosted package proofs."
    )
    parser.add_argument("--signing-proof", type=Path, default=DEFAULT_SIGNING_PROOF)
    parser.add_argument("--validation-result", type=Path, default=DEFAULT_VALIDATION_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--release-id", default="pios-core-self-hosted-qemu-arm64-20260702")
    parser.add_argument("--version", default="0.1.0-local-proof")
    parser.add_argument("--channel", default="local-proof")
    parser.add_argument("--architecture", default="arm64")
    parser.add_argument("--format", default="qcow2")
    parser.add_argument("--proof-record", default="")
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--source-tag", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    signing_proof_path = resolve_repo_path(args.signing_proof)
    validation_result_path = resolve_repo_path(args.validation_result)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    signing_proof = load_json(signing_proof_path)
    validation_result = load_json(validation_result_path)
    if signing_proof.get("status") != "passed":
        raise ValueError("signing proof must have status=passed")
    if validation_result.get("status") != "passed":
        raise ValueError("validation result must have status=passed")

    package = validation_result["package"]
    validation = validation_result["validation"]
    image = validation["image"]
    package_archive = package["package_archive"]
    signing_key = signing_proof["signing_key"]
    key_scope = signing_key.get("key_scope")
    if key_scope == "peecos_production_release_key":
        production_key_status = "production_release_key_verified"
        status = "release_candidate_signed_not_published"
        boundaries = [
            "signed release candidate manifest",
            "not published by this script",
            "no real owner data",
            "provider support is tracked by separate provider proof records",
        ]
    else:
        production_key_status = "custody_model_decided_key_not_created"
        status = "local_proof_not_published"
        boundaries = [
            "local proof manifest only",
            "not published",
            "not a production peecos release key",
            "no real owner data",
            "provider support is tracked by separate provider proof records",
        ]
    manifest = {
        "schema_version": "pios_core_self_hosted_public_release_manifest_v1",
        "created_at": utc_now(),
        "status": status,
        "release_id": args.release_id,
        "version": args.version,
        "channel": args.channel,
        "source_commit": args.source_commit or git_commit(),
        "source_tag": args.source_tag,
        "product": {
            "name": "PIOS Core Self-Hosted",
            "artifact_role": "data_empty_core_template",
            "implementation_profile": "qemu_cloud_image",
        },
        "artifact": {
            "package_name": Path(package_archive).name,
            "package_sha256": package["package_archive_sha256"],
            "image_name": Path(image).name,
            "image_sha256": validation["image_sha256"],
            "architecture": args.architecture,
            "format": args.format,
            "virtual_size": validation["inspection"]["virtual_size"],
            "actual_size": validation["inspection"]["actual_size"],
            "backing_file_present": validation["inspection"]["backing_file_present"],
        },
        "verification": {
            "checksums_file": "SHA256SUMS",
            "checksums_signature_file": "SHA256SUMS.sig",
            "signature_algorithm": "ed25519",
            "signature_verified_in_local_proof": signing_proof["signature_verified"],
            "public_key_sha256": signing_key["public_key_sha256"],
            "production_release_key_status": production_key_status,
            "key_scope": key_scope,
        },
        "proofs": {
            "package_validation": {
                "status": validation_result["status"],
                "source": public_build_artifact_ref(validation_result_path),
                "boot_proof_status": validation["boot_proof"]["status"],
            },
            "signing": {
                "status": signing_proof["status"],
                "source": public_build_artifact_ref(signing_proof_path),
            },
        },
        "proof_record": args.proof_record,
        "provider_support": {
            "local_qemu": "local_proof_passed",
            "google_cloud": "experimental",
            "azure": "unsupported",
            "aws_ec2_self_hosted": "unsupported",
            "generic_vm_providers": "unverified",
        },
        "install_entrypoints": {
            "local_qemu": "docs/install/self-hosted-qemu-local-vm.md",
            "provider_import_guidance": "docs/install/self-hosted-cloud-provider-imports.md",
        },
        "boundaries": boundaries,
    }
    output = output_dir / f"{args.release_id}-public-release-manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
