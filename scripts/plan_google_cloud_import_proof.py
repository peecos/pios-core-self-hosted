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

DEFAULT_RELEASE_MANIFEST = Path(
    "image-artifacts/qemu-public-release/"
    "pios-core-self-hosted-qemu-arm64-20260702-public-release-manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/google-cloud-import-plan")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def build_plan(
    *,
    release_manifest_path: Path,
    project_id: str,
    region: str,
    zone: str,
    staging_bucket: str,
    image_name: str,
    machine_type: str,
) -> dict[str, Any]:
    manifest = load_json(release_manifest_path)
    artifact = manifest.get("artifact", {})
    image_name_from_manifest = artifact.get("image_name")
    if not image_name_from_manifest:
        raise ValueError("release manifest artifact.image_name is required")

    architecture = artifact.get("architecture")
    image_format = artifact.get("format")
    if image_format != "qcow2":
        raise ValueError(f"expected qcow2 artifact, got {image_format!r}")
    if architecture != "arm64":
        raise ValueError(f"expected arm64 artifact for first Google Cloud plan, got {architecture!r}")

    raw_name = "disk.raw"
    archive_name = f"{Path(image_name_from_manifest).stem}-disk-raw.tar.gz"
    staging_uri = f"gs://{staging_bucket}/{archive_name}"
    instance_name = f"{image_name}-first-boot-proof"

    return {
        "schema_version": "pios_google_cloud_import_proof_plan_v1",
        "created_at": utc_now(),
        "status": "planned_zero_cloud_calls",
        "cloud_calls": 0,
        "provider": "google_cloud",
        "project_id": project_id,
        "region": region,
        "zone": zone,
        "release_manifest": str(release_manifest_path),
        "release_id": manifest.get("release_id"),
        "source_artifact": {
            "image_name": image_name_from_manifest,
            "image_sha256": artifact.get("image_sha256"),
            "architecture": architecture,
            "format": image_format,
        },
        "temporary_provider_artifacts": {
            "raw_image": raw_name,
            "raw_archive": archive_name,
            "cloud_storage_uri": staging_uri,
            "custom_image_name": image_name,
            "proof_instance_name": instance_name,
        },
        "planned_local_steps": [
            {
                "step": "convert_qcow2_to_raw",
                "command_shape": f"qemu-img convert -p -f qcow2 -O raw {image_name_from_manifest} {raw_name}",
            },
            {
                "step": "compress_raw_for_google_cloud",
                "rationale": "Google Cloud manual image import expects disk.raw inside an oldgnu tar.gz archive.",
                "command_shape": f"tar --format=oldgnu -Sczf {archive_name} {raw_name}",
            },
            {
                "step": "checksum_provider_archive",
                "command_shape": f"shasum -a 256 {archive_name}",
            },
        ],
        "planned_google_cloud_steps": [
            {
                "step": "upload_archive",
                "command_shape": f"gcloud storage cp {archive_name} {staging_uri}",
            },
            {
                "step": "create_custom_image",
                "command_shape": (
                    "gcloud compute images create "
                    f"{image_name} --project {project_id} --source-uri {staging_uri} "
                    "--architecture arm64 --guest-os-features GVNIC"
                ),
            },
            {
                "step": "create_proof_vm",
                "command_shape": (
                    "gcloud compute instances create "
                    f"{instance_name} --project {project_id} --zone {zone} "
                    f"--machine-type {machine_type} --image {image_name} "
                    "--network-interface network=default,no-address,nic-type=GVNIC"
                ),
            },
            {
                "step": "cleanup",
                "command_shape": (
                    "delete proof VM, custom image, and staging object unless owner approves repeat-proof retention"
                ),
            },
        ],
        "required_owner_approval": [
            "project_id",
            "region",
            "zone",
            "staging_bucket",
            "image_name",
            "machine_type",
            "network posture",
            "cost ceiling",
            "cleanup plan",
            "synthetic owner identity",
        ],
        "boundaries": [
            "plan only",
            "no Google Cloud calls",
            "no resource creation",
            "no owner data",
            "provider remains unsupported until proof completes",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a zero-cloud-call Google Cloud import proof.")
    parser.add_argument("--release-manifest", type=Path, default=DEFAULT_RELEASE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--project-id", default="<owner-approved-project-id>")
    parser.add_argument("--region", default="<owner-approved-region>")
    parser.add_argument("--zone", default="<owner-approved-zone>")
    parser.add_argument("--staging-bucket", default="<owner-approved-staging-bucket>")
    parser.add_argument("--image-name", default="pios-core-self-hosted-qemu-arm64-proof")
    parser.add_argument("--machine-type", default="<owner-approved-arm64-machine-type>")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    release_manifest_path = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(
        release_manifest_path=release_manifest_path,
        project_id=args.project_id,
        region=args.region,
        zone=args.zone,
        staging_bucket=args.staging_bucket,
        image_name=args.image_name,
        machine_type=args.machine_type,
    )
    output = output_dir / f"{args.image_name}-plan.json"
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
